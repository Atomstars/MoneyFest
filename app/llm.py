"""Shared LLM helper -- the ONLY place any LLM SDK is called.

Every LLM call in the system (the offline exposure drafter, the Phase-2 attribution
agent, and the verifier) goes through :func:`structured_call`. It uses **forced
tool-use** as the structured-output mechanism: we declare one tool whose input schema
is the desired JSON schema and force the model to call it, then read the call's
arguments back out. Two backends are supported, selected by ``app.config.LLM_PROVIDER``:

* ``"groq"`` (default) -- free-tier, OpenAI-compatible ``/chat/completions`` API.
  Tool forcing: ``tool_choice={"type": "function", "function": {"name": ...}}``;
  arguments arrive as a JSON *string* in ``choices[0].message.tool_calls[0].function``.
* ``"nvidia"`` -- NVIDIA NIM at integrate.api.nvidia.com, serving open-weight models
  (Llama Nemotron Super by default). Same OpenAI tool-calling shape as Groq, called
  over plain httpx. Its daily budget is far more generous than Groq's 100k-token
  ceiling, which is the limit that has repeatedly stalled golden-set validation.
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


def _openai_tool_payload(*, model: str, system: str, user: str, schema: dict,
                         tool_name: str, tool_description: str,
                         max_tokens: int) -> dict:
    """The request body shared by every OpenAI-compatible provider."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,  # structured extraction, not generation
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": schema,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
    }


def _parse_openai_tool_response(body: dict, *, model: str, tool_name: str) -> dict:
    """Pull the forced call's arguments out of an OpenAI-shaped JSON response."""
    choices = body.get("choices") or []
    if not choices:
        raise LLMError(f"model {model} returned no choices: {str(body)[:300]}")
    message = choices[0].get("message") or {}
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") != tool_name:
            continue
        args = function.get("arguments")
        if isinstance(args, dict):
            return args
        try:
            return json.loads(args)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMError(
                f"model {model} returned malformed tool arguments: {exc}"
            ) from exc
    raise LLMError(
        f"model {model} returned no tool call for {tool_name!r} "
        f"(finish_reason={choices[0].get('finish_reason')!r}). "
        f"Content was: {str(message.get('content'))[:200]!r}"
    )


def _call_nvidia(
    *, model: str, system: str, user: str, schema: dict,
    tool_name: str, tool_description: str, max_tokens: int,
) -> dict:
    """NVIDIA NIM (integrate.api.nvidia.com) via its OpenAI-compatible endpoint.

    Uses httpx directly rather than pulling in the ``openai`` SDK: the request is one
    JSON POST, httpx is already a dependency, and doing it by hand is what lets us set
    ``chat_template_kwargs`` -- which the OpenAI SDK has no typed slot for and which is
    how Nemotron's reasoning mode is switched off.

    Why thinking is off by default: Nemotron is a reasoning model, and its thinking
    preamble both burns the token budget and competes with the forced tool call for
    the output slot. Structured extraction of this kind does not need it -- the same
    reasoning that keeps Anthropic's extended thinking disabled on the other path.
    """
    import os

    import httpx

    from app.config import NVIDIA_BASE_URL, NVIDIA_REASONING_BUDGET, NVIDIA_THINKING

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise LLMError(
            "NVIDIA_API_KEY is not set. Get a key at https://build.nvidia.com/ "
            "(free tier) and export NVIDIA_API_KEY, or select another backend with "
            "LLM_PROVIDER=groq|anthropic."
        )

    payload = _openai_tool_payload(
        model=model, system=system, user=user, schema=schema,
        tool_name=tool_name, tool_description=tool_description, max_tokens=max_tokens,
    )
    # NIM's own spelling. ``thinking`` (without the prefix) is accepted and silently
    # ignored, so the wrong key looks like it works while changing nothing.
    payload["chat_template_kwargs"] = {"enable_thinking": NVIDIA_THINKING}
    if NVIDIA_THINKING:
        payload["reasoning_budget"] = NVIDIA_REASONING_BUDGET

    last_exc: Exception | None = None
    for attempt in range(GROQ_MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}",
                         "Accept": "application/json"},
                timeout=GROQ_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - network variance
            last_exc = exc
            if attempt == GROQ_MAX_RETRIES:
                raise LLMError(f"NVIDIA NIM request failed: {exc}") from exc
            time.sleep(GROQ_RETRY_FALLBACK_SECONDS)
            continue

        if resp.status_code == 429:
            # Same hard cap as Groq: a multi-hour retry-after is a daily quota, and
            # sleeping through it presents as a hang rather than an error.
            wait = GROQ_RETRY_FALLBACK_SECONDS
            try:
                wait = float(resp.headers.get("retry-after", wait))
            except (TypeError, ValueError):
                pass
            if wait > GROQ_RETRY_MAX_WAIT_SECONDS or attempt == GROQ_MAX_RETRIES:
                raise LLMError(
                    f"NVIDIA NIM rate-limited model {model} (server asked for "
                    f"{wait:.0f}s). Not waiting -- retry later or switch LLM_PROVIDER."
                )
            time.sleep(wait)
            continue

        if resp.status_code >= 400:
            raise LLMError(
                f"NVIDIA NIM returned HTTP {resp.status_code} for model {model}: "
                f"{resp.text[:400]}"
            )
        return _parse_openai_tool_response(resp.json(), model=model, tool_name=tool_name)

    raise LLMError(f"NVIDIA NIM call to {model} failed after retries: {last_exc}")


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
    if provider == "nvidia":
        return _call_nvidia(
            model=model, system=system, user=user, schema=schema,
            tool_name=tool_name, tool_description=tool_description,
            max_tokens=max_tokens,
        )
    if provider == "anthropic":
        return _call_anthropic_shaped(
            _anthropic_client(), model=model, system=system, user=user, schema=schema,
            tool_name=tool_name, tool_description=tool_description,
            max_tokens=max_tokens,
        )
    raise LLMError(
        f"unknown LLM_PROVIDER {provider!r} "
        f"(expected 'groq', 'nvidia' or 'anthropic')"
    )


def _self_check() -> int:  # pragma: no cover - operator tool
    """``python -m app.llm --check`` -- prove a provider can do forced tool-use.

    Worth running before any golden-set run on a new backend. A provider that chats
    fine but cannot reliably return a forced tool call is useless here: every call in
    this system depends on structured output, and the failure would otherwise surface
    as a confusing mid-run parse error.
    """
    import argparse

    from app.config import ATTRIBUTION_MODEL, LLM_PROVIDER

    parser = argparse.ArgumentParser(description="Check an LLM backend end to end.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--provider", default=LLM_PROVIDER)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model = args.model or ATTRIBUTION_MODEL
    print(f"provider={args.provider}  model={model}")
    schema = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "direction": {"type": "string", "enum": ["up", "down"]},
        },
        "required": ["ticker", "direction"],
    }
    try:
        out = structured_call(
            model=model,
            system="Extract the ticker and direction. Return only the tool call.",
            user="TCS closed 2.8% lower today.",
            schema=schema,
            tool_name="emit_move",
            provider=args.provider,
        )
    except LLMError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"ok -> {out}")
    if out.get("direction") != "down":
        print("WARNING: forced tool-use worked but the answer is wrong; "
              "validate against the golden set before trusting this model.")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_self_check())
