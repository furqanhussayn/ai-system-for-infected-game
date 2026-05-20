from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import time

import httpx

from src.core import config


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    keyId: str = ""
    statusCode: int | None = None
    errorType: str = ""
    errorMessage: str = ""
    stage: str = ""
    rawPreview: str = ""
    latencyMs: int = 0
    attemptCount: int = 0
    llmUsed: bool = False
    failureChain: list[dict[str, object]] = field(default_factory=list)


_TRANSIENT_STAGES = {"rate_limited", "provider_capacity", "server_error", "timeout", "empty_response", "adapter_exception"}


def _safe_preview(value: str | None, limit: int = 180) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("\n", " ").replace("\r", " ")
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def _prompt_to_text(prompt_or_messages: object) -> str:
    if isinstance(prompt_or_messages, str):
        return prompt_or_messages
    if isinstance(prompt_or_messages, list):
        parts: list[str] = []
        for item in prompt_or_messages:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                role = str(item.get("role", "user")).strip()
                content = item.get("content", "")
                if isinstance(content, list):
                    content = " ".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
                parts.append(f"{role}: {content}")
                continue
            parts.append(str(item))
        return "\n".join(part for part in parts if str(part).strip())
    return str(prompt_or_messages)


def _failure_result(
    *,
    provider: str,
    model: str,
    stage: str,
    status_code: int | None = None,
    error_type: str = "",
    error_message: str = "",
    raw_preview: str = "",
    latency_ms: int = 0,
    attempt_count: int = 0,
    key_id: str = "",
    failure_chain: list[dict[str, object]] | None = None,
) -> LLMResult:
    return LLMResult(
        ok=False,
        text="",
        provider=provider,
        model=model,
        statusCode=status_code,
        errorType=error_type,
        errorMessage=_safe_preview(error_message),
        stage=stage,
        rawPreview=_safe_preview(raw_preview),
        latencyMs=latency_ms,
        attemptCount=attempt_count,
        keyId=key_id,
        llmUsed=False,
        failureChain=failure_chain or [],
    )


def _success_result(
    *,
    provider: str,
    model: str,
    text: str,
    raw_preview: str,
    latency_ms: int,
    attempt_count: int,
    key_id: str = "",
    failure_chain: list[dict[str, object]] | None = None,
) -> LLMResult:
    clean_text = (text or "").strip()
    return LLMResult(
        ok=bool(clean_text),
        text=clean_text,
        provider=provider,
        model=model,
        statusCode=200 if clean_text else None,
        errorType="",
        errorMessage="",
        stage="success" if clean_text else "empty_response",
        rawPreview=_safe_preview(raw_preview or clean_text),
        latencyMs=latency_ms,
        attemptCount=attempt_count,
        keyId=key_id,
        llmUsed=bool(clean_text),
        failureChain=failure_chain or [],
    )


def _http_stage_from_status(status_code: int) -> str:
    if status_code == 401:
        return "invalid_api_key"
    if status_code == 403:
        return "forbidden_or_no_model_permission"
    if status_code == 429:
        return "rate_limited"
    if status_code == 498:
        return "provider_capacity"
    if status_code in (500, 502, 503):
        return "server_error"
    return "http_error"


def _should_retry(stage: str) -> bool:
    return stage in _TRANSIENT_STAGES


def _provider_identity() -> tuple[str, str]:
    provider = str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower() or "groq"
    model = config.GROQ_MODEL if provider == "groq" else config.GEMINI_MODEL
    return provider, model


async def _generate_groq_chat_response_result(
    prompt_or_messages: object,
    *,
    timeout_seconds: int,
    model: str | None = None,
    api_key: str | None = None,
    key_id: str = "",
    max_output_tokens: int = 80,
    temperature: float = 0.8,
    failure_chain: list[dict[str, object]] | None = None,
) -> LLMResult:
    provider = "groq"
    model = (model or config.GROQ_MODEL or config.GROQ_CHAT_MODEL).strip()
    api_key = str(api_key or config.GROQ_API_KEY or "").strip()
    prompt = _prompt_to_text(prompt_or_messages)
    if not api_key:
        return _failure_result(provider=provider, model=model, stage="missing_api_key", error_message="Groq API key is not configured.", key_id=key_id, failure_chain=failure_chain)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": int(max_output_tokens or getattr(config, "LLM_MAX_OUTPUT_TOKENS", 80)),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(GROQ_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        status_code = response.status_code
        if status_code >= 400:
            try:
                error_preview = response.text
            except Exception:
                error_preview = ""
            return _failure_result(
                provider=provider,
                model=model,
                stage=_http_stage_from_status(status_code),
                status_code=status_code,
                error_type=_http_stage_from_status(status_code),
                error_message=_safe_preview(error_preview or f"HTTP {status_code}"),
                raw_preview=error_preview,
                latency_ms=latency_ms,
                key_id=key_id,
                failure_chain=failure_chain,
            )

        try:
            data = response.json()
        except Exception as exc:
            return _failure_result(
                provider=provider,
                model=model,
                stage="invalid_json",
                status_code=status_code,
                error_type=type(exc).__name__,
                error_message="Provider response was not valid JSON.",
                raw_preview=response.text if hasattr(response, "text") else "",
                latency_ms=latency_ms,
                key_id=key_id,
                failure_chain=failure_chain,
            )

        choices = data.get("choices") or []
        if not choices:
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="No chat choices returned.", latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="Chat content was missing.", latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)

        content = content.strip()
        if not content:
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="Chat content was empty.", latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)

        return _success_result(provider=provider, model=model, text=content, raw_preview=content, latency_ms=latency_ms, attempt_count=1, key_id=key_id, failure_chain=failure_chain or [])

    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="timeout", error_type="TimeoutException", error_message=f"Request timed out after {timeout_seconds}s.", latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)
    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        status_code = exc.response.status_code if exc.response is not None else None
        raw_preview = exc.response.text if exc.response is not None else ""
        return _failure_result(
            provider=provider,
            model=model,
            stage=_http_stage_from_status(status_code or 0),
            status_code=status_code,
            error_type=type(exc).__name__,
            error_message=_safe_preview(raw_preview or str(exc)),
            raw_preview=raw_preview,
            latency_ms=latency_ms,
            key_id=key_id,
            failure_chain=failure_chain,
        )
    except httpx.RequestError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="http_error", error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="adapter_exception", error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms, key_id=key_id, failure_chain=failure_chain)


async def _generate_gemini_chat_response_result(prompt_or_messages: object, *, timeout_seconds: int) -> LLMResult:
    provider = "gemini"
    model = config.GEMINI_MODEL.strip() or "gemini-1.5-flash"
    api_key = config.GEMINI_API_KEY.strip()
    if not api_key:
        return _failure_result(provider=provider, model=model, stage="missing_api_key", error_message="Gemini API key is not configured.")

    prompt = _prompt_to_text(prompt_or_messages)
    url = f"{GEMINI_GENERATE_CONTENT_URL.format(model=model)}?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0 if getattr(config, "AI_MODE", "") == "agent" else 0.8,
            "maxOutputTokens": 800 if getattr(config, "AI_MODE", "") == "agent" else 80,
        },
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        status_code = response.status_code
        if status_code >= 400:
            try:
                error_preview = response.text
            except Exception:
                error_preview = ""
            return _failure_result(
                provider=provider,
                model=model,
                stage=_http_stage_from_status(status_code),
                status_code=status_code,
                error_type="http_status_error",
                error_message=_safe_preview(error_preview or f"HTTP {status_code}"),
                raw_preview=error_preview,
                latency_ms=latency_ms,
            )

        try:
            data = response.json()
        except Exception as exc:
            return _failure_result(
                provider=provider,
                model=model,
                stage="invalid_json",
                status_code=status_code,
                error_type=type(exc).__name__,
                error_message="Provider response was not valid JSON.",
                raw_preview=response.text if hasattr(response, "text") else "",
                latency_ms=latency_ms,
            )

        candidates = data.get("candidates") or []
        if not candidates:
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="No candidates returned.", latency_ms=latency_ms)

        content = (candidates[0].get("content") or {}).get("parts") or []
        if not content:
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="Gemini content parts missing.", latency_ms=latency_ms)

        text = content[0].get("text")
        if not isinstance(text, str):
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="Gemini text missing.", latency_ms=latency_ms)

        text = text.strip()
        if not text:
            return _failure_result(provider=provider, model=model, stage="empty_response", status_code=status_code, error_message="Gemini text empty.", latency_ms=latency_ms)

        return _success_result(provider=provider, model=model, text=text, raw_preview=text, latency_ms=latency_ms, attempt_count=1)

    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="timeout", error_type="TimeoutException", error_message=f"Request timed out after {timeout_seconds}s.", latency_ms=latency_ms)
    except httpx.RequestError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="http_error", error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return _failure_result(provider=provider, model=model, stage="adapter_exception", error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms)


async def _generate_chat_response_result_core(
    prompt_or_messages: object,
    *,
    timeout_seconds: int,
    model: str | None = None,
    api_key: str | None = None,
    key_id: str = "",
    max_output_tokens: int = 80,
    temperature: float = 0.7,
    failure_chain: list[dict[str, object]] | None = None,
) -> LLMResult:
    if config.AI_MODE not in {"groq", "agent"}:
        provider, model = _provider_identity()
        return _failure_result(provider=provider, model=model, stage="mode_disabled", error_message="AI mode is disabled.")

    provider = str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower() or "groq"
    if provider == "gemini":
        return await _generate_gemini_chat_response_result(prompt_or_messages, timeout_seconds=timeout_seconds)
    return await _generate_groq_chat_response_result(
        prompt_or_messages,
        timeout_seconds=timeout_seconds,
        model=model,
        api_key=api_key,
        key_id=key_id,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        failure_chain=failure_chain,
    )


def _coerce_public_call_result(value: object) -> LLMResult:
    provider, model = _provider_identity()
    if isinstance(value, LLMResult):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return _failure_result(provider=provider, model=model, stage="empty_response", error_message="Public LLM call returned empty text.")
        return _success_result(provider=provider, model=model, text=text, raw_preview=text, latency_ms=0, attempt_count=1)
    if value is None:
        return _failure_result(provider=provider, model=model, stage="empty_response", error_message="Public LLM call returned no text.")
    return _failure_result(provider=provider, model=model, stage="adapter_exception", error_type=type(value).__name__, error_message="Unsupported public LLM call return value.")


async def generate_chat_response_result(
    prompt_or_messages: object,
    *,
    model: str | None = None,
    api_key: str | None = None,
    key_id: str = "",
    max_output_tokens: int = 80,
    temperature: float = 0.7,
    max_retries: int | None = None,
    timeout_seconds: int | None = None,
) -> LLMResult:
    public_func = globals().get("generate_chat_response")
    if public_func is not _generate_chat_response_compat:
        try:
            maybe = await public_func(prompt_or_messages)
        except Exception as exc:
            provider, model = _provider_identity()
            return _failure_result(provider=provider, model=model, stage="adapter_exception", error_type=type(exc).__name__, error_message=str(exc))
        return _coerce_public_call_result(maybe)

    timeout_seconds = timeout_seconds or getattr(config, "LLM_TIMEOUT_SECONDS", 8)
    retry_budget = max(0, int(max_retries if max_retries is not None else getattr(config, "LLM_MAX_RETRIES", 1)))

    attempt = 0
    last_result: LLMResult | None = None
    backoffs = [0.5, 1.2]

    while True:
        attempt += 1
        result = await _generate_chat_response_result_core(
            prompt_or_messages,
            timeout_seconds=timeout_seconds,
            model=model,
            api_key=api_key,
            key_id=key_id,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )
        result.attemptCount = attempt
        last_result = result

        if result.ok or not _should_retry(result.stage) or attempt > retry_budget:
            return result

        backoff_index = min(attempt - 1, len(backoffs) - 1)
        await asyncio.sleep(backoffs[backoff_index])

    return last_result or _failure_result(provider=_provider_identity()[0], model=_provider_identity()[1], stage="adapter_exception", error_message="Unknown LLM result state.")


async def _generate_chat_response_compat(prompt: str) -> str | None:
    result = await generate_chat_response_result(prompt)
    return result.text or None


async def _generate_groq_chat_response(prompt: str) -> str | None:
    api_key = config.GROQ_API_KEY.strip()
    if not api_key:
        return None

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 80,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(GROQ_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            return None
        content = content.strip()
        return content or None
    except Exception:
        return None


async def _generate_gemini_chat_response(prompt: str) -> str | None:
    api_key = config.GEMINI_API_KEY.strip()
    if not api_key:
        return None

    model = config.GEMINI_MODEL.strip() or "gemini-1.5-flash"
    url = f"{GEMINI_GENERATE_CONTENT_URL.format(model=model)}?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            # Use deterministic settings for agent-mode JSON outputs so model
            # reliably follows the strict JSON schema expected by the agent
            "temperature": 0.0 if getattr(config, "AI_MODE", "") == "agent" else 0.8,
            "maxOutputTokens": 800 if getattr(config, "AI_MODE", "") == "agent" else 80,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            return None
        text = parts[0].get("text")
        if not isinstance(text, str):
            return None
        text = text.strip()
        return text or None
    except Exception:
        return None


generate_chat_response = _generate_chat_response_compat
