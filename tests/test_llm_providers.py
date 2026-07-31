"""Provider selection and the OpenAI-compatible response parser in app/llm.py.

No network. These cover the boundary that actually breaks when a backend is swapped:
which path a provider name routes to, and whether a malformed or tool-call-free
response is reported clearly instead of surfacing as a confusing parse error
mid-golden-run.
"""

from __future__ import annotations

import pytest

from app.llm import LLMError, _parse_openai_tool_response, structured_call

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def _openai_body(arguments, name="emit", finish="tool_calls"):
    return {"choices": [{
        "message": {"tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
        "finish_reason": finish,
    }]}


def test_parses_arguments_delivered_as_a_json_string():
    """OpenAI-compatible backends send arguments as a *string*, unlike Anthropic."""
    assert _parse_openai_tool_response(
        _openai_body('{"a": 1}'), model="m", tool_name="emit") == {"a": 1}


def test_parses_arguments_already_decoded():
    assert _parse_openai_tool_response(
        _openai_body({"a": 2}), model="m", tool_name="emit") == {"a": 2}


def test_no_tool_call_reports_the_content_it_returned_instead():
    """A reasoning model that chats instead of calling the tool is the failure this
    codebase most needs named clearly -- every call here depends on forced tool-use."""
    body = {"choices": [{"message": {"content": "Let me think about this..."},
                         "finish_reason": "stop"}]}
    with pytest.raises(LLMError) as exc:
        _parse_openai_tool_response(body, model="nemotron", tool_name="emit")
    assert "no tool call" in str(exc.value)
    assert "Let me think" in str(exc.value)


def test_malformed_arguments_raise_llm_error():
    with pytest.raises(LLMError, match="malformed tool arguments"):
        _parse_openai_tool_response(_openai_body("{not json"), model="m", tool_name="emit")


def test_wrong_tool_name_is_not_accepted():
    with pytest.raises(LLMError, match="no tool call"):
        _parse_openai_tool_response(
            _openai_body('{"a": 1}', name="something_else"), model="m", tool_name="emit")


def test_empty_choices_raises():
    with pytest.raises(LLMError, match="no choices"):
        _parse_openai_tool_response({"choices": []}, model="m", tool_name="emit")


def test_unknown_provider_names_the_valid_ones():
    with pytest.raises(LLMError) as exc:
        structured_call(model="m", system="s", user="u", schema=SCHEMA, provider="bogus")
    message = str(exc.value)
    assert "groq" in message and "nvidia" in message and "anthropic" in message


def test_nvidia_without_a_key_fails_with_an_actionable_message(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with pytest.raises(LLMError) as exc:
        structured_call(model="m", system="s", user="u", schema=SCHEMA, provider="nvidia")
    assert "NVIDIA_API_KEY" in str(exc.value)


def test_injected_client_still_bypasses_provider_selection(fake_client):
    """The test-injection contract: passing client= always uses the Anthropic-shaped
    path, because every test double in this codebase mimics that shape."""
    client = fake_client({"a": 7})
    out = structured_call(model="m", system="s", user="u", schema=SCHEMA,
                          client=client, provider="nvidia")
    assert out == {"a": 7}


def test_nvidia_request_shape(monkeypatch):
    """Forced tool-use, temperature 0, and thinking disabled by default -- a reasoning
    preamble both burns budget and competes with the forced call for the output."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    captured = {}

    class _Resp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def json():
            return _openai_body('{"a": 3}')

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return _Resp()

    monkeypatch.setattr("httpx.post", fake_post)

    out = structured_call(model="nvidia/test", system="sys", user="usr",
                          schema=SCHEMA, tool_name="emit", provider="nvidia")

    assert out == {"a": 3}
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    body = captured["json"]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "emit"}}
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["tools"][0]["function"]["parameters"] == SCHEMA


def test_nvidia_http_error_surfaces_the_body(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    class _Resp:
        status_code = 400
        headers: dict = {}
        text = "model not found"

    monkeypatch.setattr("httpx.post", lambda url, **kw: _Resp())
    with pytest.raises(LLMError) as exc:
        structured_call(model="nvidia/missing", system="s", user="u",
                        schema=SCHEMA, provider="nvidia")
    assert "HTTP 400" in str(exc.value) and "model not found" in str(exc.value)


def test_nvidia_long_rate_limit_fails_fast_instead_of_sleeping(monkeypatch):
    """A multi-hour retry-after is a DAILY quota. Honouring it parks the process
    until tomorrow and presents as a hang -- the exact bug that cost a diagnostic
    detour on the Groq path (STATUS_REPORT 2.3)."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    class _Resp:
        status_code = 429
        headers = {"retry-after": "7200"}
        text = "rate limited"

    monkeypatch.setattr("httpx.post", lambda url, **kw: _Resp())

    def no_sleep(_seconds):
        raise AssertionError("must not sleep on a multi-hour retry-after")

    monkeypatch.setattr("time.sleep", no_sleep)

    with pytest.raises(LLMError, match="rate-limited"):
        structured_call(model="nvidia/test", system="s", user="u",
                        schema=SCHEMA, provider="nvidia")
