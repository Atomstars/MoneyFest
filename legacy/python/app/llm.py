"""Shared LLM helper -- the ONLY place any LLM SDK is called.

Every LLM call in the system (the offline exposure drafter, the Phase-2 attribution
agent, and the verifier) goes through :func:`structured_call`. It uses **forced
tool-use** as the structured-output mechanism: we declare one tool whose input schema
is the desired JSON schema and force the model to call it, then read the call's
arguments back out. Two backends are supported, selected by ``app.config.LLM_PROVIDER``:

* ``"groq"`` (default) -- free-tier, OpenAI-compatible ``/chat/completions`` API.
  Tool forcing: ``tool_choice={"type": "function", "function": {"name": ...}}``;
  arguments arrive as a JSON *string* in ``choices[0].message.tool_calls[0].function``.
* ``"anthropic"`` -- forced ``tool_choice={"type": "tool", "name": ...}``; arguments
  arrive already-parsed in the ``tool_use`` content block's ``input``.

Import-time note: both SDKs are imported lazily inside the call so that modules which
merely reference these helpers (and the whole daily loop) never import either unless
an LLM call is actually made -- Phase 1/daily-loop stays LLM-free.

Test-injection contract (unchanged): passing ``client=`` bypasses provider selection
entirely and always uses the Anthropic-shaped call + parse below, because every test
double in this codebase (``tests/conftest.py::FakeLLMClient``) mimics that shape. Real
provider branching only happens when ``client`` is ``None``.
"""

from __future__ import annotations

import json
import time
from typing import Any

# Groq's free tier caps llama-3.3-70b-versatile at 12,000 tokens/minute, and the
# RESERVED max_completion_tokens counts against that budget -- not just the tokens
# actually generated. So an oversized ceiling directly throttles throughput: at 4096
# reserved per call only ~2 calls/minute fit, which makes a 60-call golden run crawl
# behind 429 backoffs.
#
# Real outputs here are small (a few cited drivers, or a verdict + reason -- ~200
# tokens observed), so 2048 is already generous. The original 16000 was sized for
# Claude's far larger budget and blew through Groq's ceiling on the very first call.
DEFAULT_MAX_TOKENS = 2048

# Retry budget for Groq 429s (RateLimitError). The free tier's RPM (30) is tight enough
# that a burst of calls across several stocks in one EOD run can trip it transiently.
GROQ_MAX_RETRIES = 3
GROQ_RETRY_FALLBACK_SECONDS = 15.0

# NEVER sleep longer than this on a 429, no matter what ``retry-after`` says.
#
# Groq enforces BOTH a per-minute (TPM) and a per-day (TPD, 100k on the free tier)
# token ceiling, and both surface as a 429. A per-minute limit returns a retry-after of
# a few seconds and is worth waiting out; a *daily* limit returns hours. Honouring that
# blindly parks the process in time.sleep() until tomorrow -- it looks exactly like a
# hang (process alive, zero CPU, no progress) and is never the right behaviour for a
# batch job. Past this ceiling we fail fast with an actionable message instead.
GROQ_RETRY_MAX_WAIT_SECONDS = 60.0

# Per-request HTTP timeout. Structured extraction of this size returns in seconds.
GROQ_REQUEST_TIMEOUT_SECONDS = 60.0


class LLMError(RuntimeError):
    pass


def _anthropic_client():
    try:
        import anthropic
    except Exception as exc:  # pragma: no cover
        raise LLMError("anthropic SDK not installed") from exc
    return anthropic.Anthropic()


def _groq_client():
    try:
        import groq
    except Exception as exc:  # pragma: no cover
        raise LLMError(
            "groq SDK not installed. Run: pip install groq  (or `pip install -r "
            "requirements.txt`). Get a free API key at https://console.groq.com/keys "
            "and set GROQ_API_KEY."
        ) from exc
    try:
        # Bounded timeout and no SDK-level retries: this module does its own 429
        # handling (with a hard wait cap), and the daily loop must never block
        # indefinitely on a wedged connection.
        return groq.Groq(timeout=GROQ_REQUEST_TIMEOUT_SECONDS, max_retries=0)
    except Exception as exc:  # pragma: no cover - missing key surfaces here
        raise LLMError(
            "could not construct Groq client (is GROQ_API_KEY set?): " + str(exc)
        ) from exc


def _call_anthropic_shaped(
    cli: Any, *, model: str, system: str, user: str, schema: dict,
    tool_name: str, tool_description: str, max_tokens: int,
) -> dict:
    """The original code path: Anthropic-native request, and its test-double form.

    Note: thinking is intentionally NOT enabled -- Claude requires ``tool_choice`` to
    be ``auto`` when extended/adaptive thinking is on, and we force the tool here to
    guarantee structured output. Structured extraction of this kind does not need
    thinking.
    """
    resp = cli.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        # SDK objects expose .type/.input; dicts (test doubles) use keys.
        btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if btype == "tool_use":
            data = getattr(block, "input", None)
            if data is None and isinstance(block, dict):
                data = block.get("input")
            if isinstance(data, str):
                data = json.loads(data)
            return data
    raise LLMError(f"model {model} returned no tool_use block")


def _call_groq(
    cli: Any, *, model: str, system: str, user: str, schema: dict,
    tool_name: str, tool_description: str, max_tokens: int,
) -> dict:
    """OpenAI-compatible chat.completions.create with a forced function call.

    Retries on 429 (RateLimitError) with the server's own ``retry-after`` if it
    provides one, else a fixed backoff -- see GROQ_MAX_RETRIES.
    """
    import groq

    kwargs = dict(
        model=model,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": schema,
            },
        }],
        tool_choice={"type": "function", "function": {"name": tool_name}},
    )

    resp = None
    last_exc: Exception | None = None
    for attempt in range(GROQ_MAX_RETRIES + 1):
        try:
            resp = cli.chat.completions.create(**kwargs)
            break
        except groq.RateLimitError as exc:
            last_exc = exc
            if attempt == GROQ_MAX_RETRIES:
                break
            wait = GROQ_RETRY_FALLBACK_SECONDS
            header = getattr(getattr(exc, "response", None), "headers", None)
            if header is not None:
                try:
                    wait = float(header.get("retry-after", wait))
                except (TypeError, ValueError):
                    pass
            if wait > GROQ_RETRY_MAX_WAIT_SECONDS:
                # A multi-hour retry-after means a *daily* quota, not a transient burst.
                # Waiting it out would look like a hang; surface it instead.
                raise LLMError(
                    f"model {model} hit a long-duration rate limit "
                    f"(server asked for {wait:.0f}s / {wait / 3600:.1f}h). This is "
                    f"almost certainly the free tier's tokens-per-day quota, not a "
                    f"transient burst -- retrying now will not help. Wait for the "
                    f"daily reset, use a different key, or switch provider via "
                    f"LLM_PROVIDER. Original error: {exc}"
                ) from exc
            time.sleep(wait)
    if resp is None:
        raise LLMError(
            f"model {model} rate-limited after {GROQ_MAX_RETRIES} retries: {last_exc}"
        ) from last_exc

    choice = resp.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None) or []
    for call in tool_calls:
        if call.function.name == tool_name:
            try:
                return json.loads(call.function.arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                raise LLMError(
                    f"model {model} returned malformed tool arguments: {exc}"
                ) from exc
    raise LLMError(f"model {model} returned no tool call for {tool_name!r} "
                   f"(finish_reason={choice.finish_reason!r})")


def structured_call(
    *,
    model: str,
    system: str,
    user: str,
    schema: dict,
    tool_name: str = "emit",
    tool_description: str = "Return the result in the required structure.",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
    provider: str | None = None,
) -> dict:
    """Run one structured LLM call and return the parsed object matching ``schema``.

    ``client`` is injectable for tests (any object exposing ``.messages.create``,
    Anthropic-shaped) -- when given, provider selection is skipped entirely.

    ``provider`` selects the real backend when ``client`` is None; defaults to
    ``app.config.LLM_PROVIDER`` ("groq" unless overridden).
    """
    if client is not None:
        return _call_anthropic_shaped(
            client, model=model, system=system, user=user, schema=schema,
            tool_name=tool_name, tool_description=tool_description,
            max_tokens=max_tokens,
        )

    if provider is None:
        from app.config import LLM_PROVIDER
        provider = LLM_PROVIDER

    if provider == "groq":
        return _call_groq(
            _groq_client(), model=model, system=system, user=user, schema=schema,
            tool_name=tool_name, tool_description=tool_description,
            max_tokens=max_tokens,
        )
    if provider == "anthropic":
        return _call_anthropic_shaped(
            _anthropic_client(), model=model, system=system, user=user, schema=schema,
            tool_name=tool_name, tool_description=tool_description,
            max_tokens=max_tokens,
        )
    raise LLMError(f"unknown LLM_PROVIDER {provider!r} (expected 'groq' or 'anthropic')")
