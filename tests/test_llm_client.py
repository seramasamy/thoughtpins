from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_config_accepts_protocol_compatibility_env_fallbacks(monkeypatch):
    from thoughtpins import config as config_module

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://llm.example.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "vendor-chat[large]")

    assert config_module._llm_api_key() == "test-token"
    assert config_module._llm_base_url() == "https://llm.example.com"
    assert config_module._llm_model() == "vendor-chat[large]"


def test_config_prefers_generic_llm_env(monkeypatch):
    from thoughtpins import config as config_module

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "generic-token")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "vendor-model")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "compat-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://compat.example.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "compat-model")

    assert config_module._llm_provider() == "openai_compatible"
    assert config_module._llm_api_key() == "generic-token"
    assert config_module._llm_base_url() == "https://llm.example.com/v1"
    assert config_module._llm_model() == "vendor-model"


def test_generic_llm_client_import_is_primary():
    from thoughtpins.llm.client import OpenAICompatibleLLMClient, get_llm_client

    assert OpenAICompatibleLLMClient.__name__ == "OpenAICompatibleLLMClient"
    assert callable(get_llm_client)


def test_llm_chat_retries_plain_variant_after_empty_configured_response(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = "" if "extra_body" in kwargs else "plain fallback ok"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "fallback-chat"
    client._extraction_model = "fallback-chat"
    client._thinking = True
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 2)

    response = client.chat([{"role": "user", "content": "hello"}], temperature=0, max_tokens=64)

    assert response == "plain fallback ok"
    assert "extra_body" in calls[0]
    assert "extra_body" not in calls[1]


def test_llm_chat_retries_plain_variant_after_exception(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if "extra_body" in kwargs:
                raise TimeoutError("temporary timeout")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="plain recovered"))])

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "fallback-chat"
    client._extraction_model = "fallback-chat"
    client._thinking = True
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 2)

    response = client.chat([{"role": "user", "content": "hello"}], temperature=0, max_tokens=64)

    assert response == "plain recovered"
    assert "extra_body" in calls[0]
    assert "extra_body" not in calls[1]


def test_llm_chat_uses_model_fallback_after_primary_failures(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if kwargs["model"] == "fallback-chat":
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="fallback model ok"))])
            raise TimeoutError("primary model timeout")

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "fallback-chat"
    client._thinking = True
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(type(config), "LLM_MAX_RETRIES", 1)

    response = client.chat([{"role": "user", "content": "hello"}], temperature=0, max_tokens=64)

    assert response == "fallback model ok"
    assert [call["model"] for call in calls] == ["primary-test", "primary-test", "fallback-chat"]
    assert "extra_body" not in calls[2]


def test_llm_chat_fails_fast_for_non_retryable_billing_response(monkeypatch):
    import pytest

    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls = 0

    class BillingError(RuntimeError):
        status_code = 402

    class FakeCompletions:
        def create(self, **kwargs):
            nonlocal calls
            calls += 1
            raise BillingError("account cannot accept requests")

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "primary-test"
    client._extraction_model = "primary-test"
    client._thinking = False
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 4)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 4)

    with pytest.raises(BillingError):
        client.chat([{"role": "user", "content": "hello"}], max_tokens=64)

    assert calls == 1


def test_llm_chat_retries_rate_limit_response(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls = 0

    class RateLimitError(RuntimeError):
        status_code = 429

    class FakeCompletions:
        def create(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RateLimitError("retry later")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="recovered"))])

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "primary-test"
    client._extraction_model = "primary-test"
    client._thinking = False
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)

    assert client.chat([{"role": "user", "content": "hello"}], max_tokens=64) == "recovered"
    assert calls == 2


@pytest.mark.parametrize("supports_thinking", [False, True])
def test_llm_extract_json_disables_thinking_for_structured_calls(monkeypatch, supports_thinking):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "fallback-chat"
    client._extraction_model = "fallback-chat"
    client._thinking = True
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EXTRACTION_MAX_TOKENS", 1234)
    monkeypatch.setattr(type(config), "LLM_EXTRACTION_MAX_TOKENS", 1234)

    monkeypatch.setattr(config, "LLM_SUPPORTS_THINKING", supports_thinking)
    result = client.extract_json("system", "user", "{}")

    assert result == {"ok": True}
    assert calls[0]["model"] == "fallback-chat"
    assert calls[0]["max_tokens"] == 1234
    assert calls[0]["response_format"] == {"type": "json_object"}
    if supports_thinking:
        assert calls[0]["extra_body"]["thinking"] == {"type": "disabled"}
    else:
        assert "extra_body" not in calls[0]


def test_llm_chat_drops_unsupported_json_mode_without_provider_coupling(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.llm.client import OpenAICompatibleLLMClient

    calls: list[dict] = []

    class UnsupportedFormatError(RuntimeError):
        status_code = 400

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if "response_format" in kwargs:
                raise UnsupportedFormatError("unsupported response format")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    client = OpenAICompatibleLLMClient.__new__(OpenAICompatibleLLMClient)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    client._model = "primary-test"
    client._fallback_model = "primary-test"
    client._extraction_model = "primary-test"
    client._thinking = False
    client._reasoning_effort = "high"

    monkeypatch.setattr(config, "LLM_EMPTY_RESPONSE_RETRIES", 2)
    monkeypatch.setattr(type(config), "LLM_EMPTY_RESPONSE_RETRIES", 2)

    response = client.chat(
        [{"role": "user", "content": "return json"}],
        response_format={"type": "json_object"},
    )

    assert response == '{"ok": true}'
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_json_parser_repairs_common_model_syntax_damage() -> None:
    from thoughtpins.llm.openai_compatible_client import _parse_json

    damaged = 'Commentary before {"users":[{"name":"Ada","role":"admin",}],"ok":true'
    assert _parse_json(damaged) == {
        "users": [{"name": "Ada", "role": "admin"}],
        "ok": True,
    }


def test_json_parser_rejects_non_object_roots() -> None:
    from thoughtpins.llm.openai_compatible_client import _parse_json

    assert _parse_json('[{"memory":"not an extraction object"}]') is None
