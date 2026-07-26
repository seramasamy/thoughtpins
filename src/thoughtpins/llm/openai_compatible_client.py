"""OpenAI-compatible LLM client with provider-specific compatibility hooks."""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Optional

from loguru import logger
from openai import OpenAI

from thoughtpins.config import config
from thoughtpins.tenancy import get_current_tenant_id
from thoughtpins.usage import ensure_budget_available, record_llm_usage


def _record_provider_usage(response: Any, *, operation: str, requested_model: str) -> None:
    """Meter one provider call from its own usage block.

    Called per attempt rather than per :meth:`chat` call: the retry/fallback loop
    below can hit the provider several times and each hit is billed separately.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    record_llm_usage(
        user_id=get_current_tenant_id(),
        provider=config.LLM_PROVIDER,
        model=getattr(response, "model", "") or requested_model,
        operation=operation,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
    )


class OpenAICompatibleLLMClient:
    """OpenAI-compatible chat client."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL.rstrip("/"),
            timeout=max(5, config.LLM_TIMEOUT_SECONDS),
            # Keep retries here explicit so configured/plain fallback happens promptly.
            max_retries=0,
        )
        self._provider = config.LLM_PROVIDER
        self._configured_model = config.LLM_MODEL
        self._model = normalize_llm_model_name(config.LLM_MODEL)
        self._fallback_model = normalize_llm_model_name(config.LLM_FALLBACK_MODEL)
        self._extraction_model = normalize_llm_model_name(config.LLM_EXTRACTION_MODEL)
        if self._model != self._configured_model:
            logger.info("Normalized configured chat runtime label")
        if self._fallback_model and self._fallback_model != self._model:
            logger.info("LLM fallback runtime configured")
        if self._extraction_model and self._extraction_model != self._model:
            logger.info("LLM extraction runtime configured")
        self._thinking = config.LLM_THINKING == "enabled" and config.LLM_SUPPORTS_THINKING
        self._reasoning_effort = config.LLM_REASONING_EFFORT

    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
        use_thinking: bool | None = None,
        model_override: str | None = None,
        operation: str = "chat",
    ) -> str:
        ensure_budget_available(get_current_tenant_id())
        primary_model = normalize_llm_model_name(model_override) if model_override else self._model
        extra_body: dict[str, Any] = {}
        thinking_enabled = self._thinking if use_thinking is None else use_thinking
        if thinking_enabled:
            extra_body["thinking"] = {"type": "enabled"}
        if thinking_enabled and self._reasoning_effort:
            extra_body["reasoning_effort"] = self._reasoning_effort

        kwargs: dict[str, Any] = {
            "model": primary_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max(max_tokens, 64) if self._thinking else max_tokens,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        if response_format:
            kwargs["response_format"] = response_format

        logger.debug("LLM call msg_count={} override={}", len(messages), bool(model_override))

        total_attempts = max(
            max(1, config.LLM_EMPTY_RESPONSE_RETRIES),
            max(0, config.LLM_MAX_RETRIES) + 1,
        )
        attempt_kwargs: list[dict[str, Any]] = []

        def add_variant(candidate: dict[str, Any]) -> None:
            if candidate not in attempt_kwargs:
                attempt_kwargs.append(candidate)

        add_variant(kwargs)
        if extra_body:
            fallback_kwargs = dict(kwargs)
            fallback_kwargs.pop("extra_body", None)
            add_variant(fallback_kwargs)
        if response_format:
            fallback_kwargs = dict(kwargs)
            fallback_kwargs.pop("response_format", None)
            add_variant(fallback_kwargs)
            if extra_body:
                plain_kwargs = dict(fallback_kwargs)
                plain_kwargs.pop("extra_body", None)
                add_variant(plain_kwargs)
        if self._fallback_model and self._fallback_model != primary_model:
            model_fallback_kwargs = dict(kwargs)
            model_fallback_kwargs["model"] = self._fallback_model
            model_fallback_kwargs.pop("extra_body", None)
            add_variant(model_fallback_kwargs)
            if response_format:
                plain_model_fallback = dict(model_fallback_kwargs)
                plain_model_fallback.pop("response_format", None)
                add_variant(plain_model_fallback)
            total_attempts = max(total_attempts, len(attempt_kwargs))
        total_attempts = max(total_attempts, len(attempt_kwargs))

        content = ""
        last_error: Exception | None = None
        for attempt in range(total_attempts):
            current_kwargs = attempt_kwargs[attempt % len(attempt_kwargs)]
            if current_kwargs.get("model") == self._fallback_model and self._fallback_model != primary_model:
                variant = "model-fallback"
            else:
                variant = "plain" if "extra_body" not in current_kwargs else "configured"
            try:
                response = self._client.chat.completions.create(**current_kwargs)
                _record_provider_usage(
                    response,
                    operation=operation,
                    requested_model=str(current_kwargs.get("model") or primary_model),
                )
                content = response.choices[0].message.content or ""
                last_error = None
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM call failed (attempt {}, {}): {}",
                    attempt + 1,
                    variant,
                    _redact_runtime_identifiers(str(exc))[:200],
                )
                content = ""
                has_untried_variant = attempt + 1 < len(attempt_kwargs)
                if not _should_retry_llm_error(exc, has_untried_variant=has_untried_variant):
                    raise
            logger.debug("LLM response length={} (attempt {}, {})", len(content), attempt + 1, variant)
            if content.strip():
                return content
            if attempt < total_attempts - 1:
                import time

                time.sleep(min(2, max(0.1, config.LLM_TIMEOUT_SECONDS / 30)))
                logger.debug("Empty response, retrying...")

        if last_error is not None:
            raise last_error
        return content

    def extract_json(self, system_prompt: str, user_prompt: str, schema_json: str) -> dict:
        """Call LLM for structured JSON extraction. Retries once with repair prompt on failure."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw = self.chat(
            messages,
            temperature=0.0,
            max_tokens=config.LLM_EXTRACTION_MAX_TOKENS,
            response_format={"type": "json_object"},
            use_thinking=False,
            model_override=self._extraction_model,
            operation="extraction",
        )
        result = _parse_json(raw)
        if result is not None:
            return result

        logger.warning("First JSON parse failed, retrying with repair prompt")
        repair_user = (
            f"{user_prompt}\n\nYour previous response was not valid JSON. "
            f"Return ONLY valid JSON matching the schema. No markdown, no commentary."
        )
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": repair_user})
        raw2 = self.chat(
            messages,
            temperature=0.0,
            max_tokens=config.LLM_EXTRACTION_MAX_TOKENS,
            response_format={"type": "json_object"},
            use_thinking=False,
            model_override=self._extraction_model,
            operation="extraction",
        )
        result2 = _parse_json(raw2)
        if result2 is not None:
            return result2

        logger.error("JSON extraction failed after retry")
        return {"entry_summary": "Extraction failed", "entry_type": "journal_entry"}

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Get embeddings from the configured OpenAI-compatible endpoint when available."""
        requested_model = model or config.LLM_MODEL
        ensure_budget_available(get_current_tenant_id())
        try:
            response = self._client.embeddings.create(
                model=requested_model,
                input=texts,
            )
        except Exception as e:
            logger.debug("LLM embedding API failed ({}), using fallback", _redact_runtime_identifiers(str(e))[:200])
            # The local hash fallback costs nothing, so it is deliberately unmetered.
            return self._fallback_embed(texts)
        _record_provider_usage(response, operation="embedding", requested_model=requested_model)
        return [d.embedding for d in response.data]

    def _fallback_embed(self, texts: list[str]) -> list[list[float]]:
        """Simple hash-based fallback when embedding API is unavailable."""
        import hashlib

        vectors = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [(b / 255.0) * 2 - 1 for b in h[:256]]
            if len(vec) < 256:
                vec.extend([0.0] * (256 - len(vec)))
            vectors.append(vec[:256])
        return vectors


def _redact_runtime_identifiers(message: str) -> str:
    """Remove configured runtime identifiers from loggable provider errors."""
    redacted = message
    for value in (
        getattr(config, "LLM_MODEL", ""),
        getattr(config, "LLM_FALLBACK_MODEL", ""),
        getattr(config, "LLM_EXTRACTION_MODEL", ""),
        getattr(config, "LLM_BASE_URL", ""),
    ):
        if value:
            redacted = redacted.replace(str(value), "[configured-runtime]")
    return redacted


def _should_retry_llm_error(error: Exception, *, has_untried_variant: bool) -> bool:
    """Classify provider failures without coupling to one SDK exception tree."""
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
    if not isinstance(status, int):
        return True
    if status in {401, 402, 403}:
        return False
    if status in {400, 404, 405, 413, 415, 422}:
        return has_untried_variant
    if status in {408, 409, 425, 429} or status >= 500:
        return True
    return False


def normalize_llm_model_name(model: str) -> str:
    """Normalize display labels such as vendor-chat[large] into API model IDs."""
    normalized = (model or "").strip().strip("\"'")
    normalized = re.sub(r"\[[^\]]+\]$", "", normalized).strip()
    return normalized or "chat-model"


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from LLM output, with repair attempts."""
    from thoughtpins.llm.json_repair import repair_json

    repaired = repair_json(raw)
    try:
        decoded = json.loads(repaired)
    except json.JSONDecodeError:
        pass
    else:
        return decoded if isinstance(decoded, dict) else None

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        decoded = json.loads(text)
        return decoded if isinstance(decoded, dict) else None
    except json.JSONDecodeError:
        return None


_client: Optional[OpenAICompatibleLLMClient] = None
_client_lock = threading.Lock()


def get_llm_client() -> OpenAICompatibleLLMClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAICompatibleLLMClient()
    return _client


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Convenience function: get embeddings for texts."""
    return get_llm_client().embed(texts)
