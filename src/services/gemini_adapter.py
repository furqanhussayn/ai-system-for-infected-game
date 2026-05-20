from __future__ import annotations

from dataclasses import dataclass
import asyncio
from datetime import datetime, timezone
import time

import httpx

from src.core import config


GEMINI_GENERATE_CONTENT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass
class _GeminiStatus:
    cooldown_until: float = 0.0
    last_error: str = ""
    last_success_at: float = 0.0
    last_failed_at: float = 0.0


_STATUS = _GeminiStatus()


def _now() -> float:
    return time.time()


def _iso(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


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


def _success_result(*, model: str, text: str, latency_ms: int, attempt_count: int, failure_chain: list[dict[str, object]] | None = None):
    from src.services.llm_adapter import LLMResult

    clean_text = (text or "").strip()
    return LLMResult(
        ok=bool(clean_text),
        text=clean_text,
        provider="gemini",
        model=model,
        keyId="",
        statusCode=200 if clean_text else None,
        errorType="",
        errorMessage="",
        stage="success" if clean_text else "empty_response",
        rawPreview=_safe_preview(clean_text),
        latencyMs=latency_ms,
        attemptCount=attempt_count,
        llmUsed=bool(clean_text),
        failureChain=failure_chain or [],
    )


def _failure_result(*, model: str, stage: str, status_code: int | None = None, error_message: str = "", error_type: str = "", latency_ms: int = 0, attempt_count: int = 0, failure_chain: list[dict[str, object]] | None = None):
    from src.services.llm_adapter import LLMResult

    return LLMResult(
        ok=False,
        text="",
        provider="gemini",
        model=model,
        keyId="",
        statusCode=status_code,
        errorType=error_type or stage,
        errorMessage=_safe_preview(error_message),
        stage=stage,
        rawPreview=_safe_preview(error_message),
        latencyMs=latency_ms,
        attemptCount=attempt_count,
        llmUsed=False,
        failureChain=failure_chain or [],
    )


def mark_gemini_success() -> None:
    now = _now()
    _STATUS.last_success_at = now
    _STATUS.last_error = ""
    _STATUS.last_failed_at = 0.0
    _STATUS.cooldown_until = 0.0


def mark_gemini_failed(reason: str, cooldown_seconds: int = 0) -> None:
    now = _now()
    cooldown = max(0, int(cooldown_seconds or 0))
    _STATUS.last_failed_at = now
    _STATUS.last_error = str(reason or "")
    _STATUS.cooldown_until = now + cooldown if cooldown else now


def get_gemini_status() -> dict[str, object]:
    now = _now()
    return {
        "configured": bool(config.GEMINI_API_KEY.strip()),
        "model": config.GEMINI_CHAT_MODEL,
        "backupModel": config.GEMINI_BACKUP_CHAT_MODEL,
        "cooldownActive": _STATUS.cooldown_until > now,
        "lastError": _STATUS.last_error,
        "lastSuccessAt": _iso(_STATUS.last_success_at),
        "lastFailedAt": _iso(_STATUS.last_failed_at),
    }


def _map_http_stage(status_code: int) -> str:
    if status_code == 401:
        return "invalid_api_key"
    if status_code == 403:
        return "invalid_api_key"
    if status_code == 429:
        return "rate_limited"
    if status_code in (500, 502, 503):
        return "server_error"
    if status_code == 404:
        return "model_unavailable"
    if status_code == 400:
        return "model_unavailable"
    return "adapter_exception"


def _map_exception_stage(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "deadline" in message:
        return "timeout"
    if "quota" in message or "rate" in message or "429" in message:
        return "rate_limited"
    if "model" in message and ("not found" in message or "unavailable" in message):
        return "model_unavailable"
    if "safety" in message or "blocked" in message:
        return "safety_blocked"
    return "adapter_exception"


async def _sdk_generate(prompt: str, *, api_key: str, model: str, max_output_tokens: int, temperature: float) -> tuple[str, str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip(), "success"
    return "", "empty_response"


async def _http_generate(prompt: str, *, api_key: str, model: str, max_output_tokens: int, temperature: float) -> tuple[str, int, str]:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }
    url = f"{GEMINI_GENERATE_CONTENT_URL.format(model=model)}?key={api_key}"
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=int(getattr(config, "LLM_TIMEOUT_SECONDS", 8))) as client:
        response = await client.post(url, json=payload)
    latency_ms = int((time.perf_counter() - start) * 1000)
    status_code = getattr(response, "status_code", None)
    if status_code and status_code >= 400:
        return "", latency_ms, _map_http_stage(status_code)
    try:
        data = response.json()
    except Exception:
        return "", latency_ms, "adapter_exception"
    candidates = data.get("candidates") or []
    if not candidates:
        return "", latency_ms, "empty_response"
    content = (candidates[0].get("content") or {}).get("parts") or []
    if not content:
        return "", latency_ms, "empty_response"
    text = content[0].get("text")
    if not isinstance(text, str) or not text.strip():
        return "", latency_ms, "empty_response"
    return text.strip(), latency_ms, "success"


async def generate_chat_response(
    prompt_or_messages,
    *,
    model=None,
    api_key=None,
    max_output_tokens=80,
    temperature=0.7,
) -> object:
    from src.services.llm_adapter import LLMResult

    prompt = _prompt_to_text(prompt_or_messages)
    api_key_value = str(api_key or config.GEMINI_API_KEY or "").strip()
    if not api_key_value:
        return _failure_result(model=str(model or config.GEMINI_CHAT_MODEL or config.GEMINI_MODEL), stage="missing_api_key", error_message="Gemini API key is not configured.")

    primary_model = str(model or config.GEMINI_CHAT_MODEL or config.GEMINI_MODEL).strip()
    start = time.perf_counter()
    try:
        try:
            text, gemini_stage = await _sdk_generate(prompt, api_key=api_key_value, model=primary_model, max_output_tokens=max_output_tokens, temperature=temperature)
            latency_ms = int((time.perf_counter() - start) * 1000)
            if gemini_stage == "success":
                mark_gemini_success()
                return _success_result(model=primary_model, text=text, latency_ms=latency_ms, attempt_count=1)
            if gemini_stage == "model_unavailable" and config.GEMINI_BACKUP_CHAT_MODEL and config.GEMINI_BACKUP_CHAT_MODEL != primary_model:
                backup_start = time.perf_counter()
                backup_text, backup_stage = await _sdk_generate(prompt, api_key=api_key_value, model=config.GEMINI_BACKUP_CHAT_MODEL, max_output_tokens=max_output_tokens, temperature=temperature)
                backup_latency = int((time.perf_counter() - backup_start) * 1000)
                if backup_stage == "success":
                    mark_gemini_success()
                    return _success_result(model=config.GEMINI_BACKUP_CHAT_MODEL, text=backup_text, latency_ms=backup_latency, attempt_count=2, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": "model_unavailable"}])
                mark_gemini_failed(backup_stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)) if backup_stage in {"invalid_api_key", "timeout", "server_error", "rate_limited"} else 0)
                return _failure_result(model=config.GEMINI_BACKUP_CHAT_MODEL, stage=backup_stage, error_message="Gemini backup model failed.", latency_ms=backup_latency, attempt_count=2, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": "model_unavailable"}, {"provider": "gemini", "model": config.GEMINI_BACKUP_CHAT_MODEL, "stage": backup_stage}])
            if gemini_stage in {"rate_limited", "timeout", "server_error", "invalid_api_key", "model_unavailable"}:
                mark_gemini_failed(gemini_stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)) if gemini_stage != "model_unavailable" else 0)
            return _failure_result(model=primary_model, stage=gemini_stage, error_message="Gemini request failed.", latency_ms=latency_ms, attempt_count=1, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": gemini_stage}])
        except ImportError:
            pass

        text, latency_ms, gemini_stage = await _http_generate(prompt, api_key=api_key_value, model=primary_model, max_output_tokens=max_output_tokens, temperature=temperature)
        if gemini_stage == "success":
            mark_gemini_success()
            return _success_result(model=primary_model, text=text, latency_ms=latency_ms, attempt_count=1)
        if gemini_stage == "model_unavailable" and config.GEMINI_BACKUP_CHAT_MODEL and config.GEMINI_BACKUP_CHAT_MODEL != primary_model:
            backup_text, backup_latency, backup_stage = await _http_generate(prompt, api_key=api_key_value, model=config.GEMINI_BACKUP_CHAT_MODEL, max_output_tokens=max_output_tokens, temperature=temperature)
            if backup_stage == "success":
                mark_gemini_success()
                return _success_result(model=config.GEMINI_BACKUP_CHAT_MODEL, text=backup_text, latency_ms=backup_latency, attempt_count=2, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": "model_unavailable"}])
            mark_gemini_failed(backup_stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)) if backup_stage in {"invalid_api_key", "timeout", "server_error", "rate_limited"} else 0)
            return _failure_result(model=config.GEMINI_BACKUP_CHAT_MODEL, stage=backup_stage, error_message="Gemini backup model failed.", latency_ms=backup_latency, attempt_count=2, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": "model_unavailable"}, {"provider": "gemini", "model": config.GEMINI_BACKUP_CHAT_MODEL, "stage": backup_stage}])
        if gemini_stage in {"rate_limited", "timeout", "server_error", "invalid_api_key", "model_unavailable"}:
            mark_gemini_failed(gemini_stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)) if gemini_stage != "model_unavailable" else 0)
        return _failure_result(model=primary_model, stage=gemini_stage, error_message="Gemini request failed.", latency_ms=latency_ms, attempt_count=1, failure_chain=[{"provider": "gemini", "model": primary_model, "stage": gemini_stage}])
    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start) * 1000)
        mark_gemini_failed("timeout", int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)))
        return _failure_result(model=primary_model, stage="timeout", error_type="TimeoutException", error_message="Gemini request timed out.", latency_ms=latency_ms, attempt_count=1)
    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        stage = _map_exception_stage(exc)
        mark_gemini_failed(stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)))
        return _failure_result(model=primary_model, stage=stage, error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms, attempt_count=1)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        stage = _map_exception_stage(exc)
        if stage in {"rate_limited", "timeout", "server_error", "invalid_api_key"}:
            mark_gemini_failed(stage, int(getattr(config, "LLM_KEY_COOLDOWN_SECONDS", 600)))
        return _failure_result(model=primary_model, stage=stage, error_type=type(exc).__name__, error_message=str(exc), latency_ms=latency_ms, attempt_count=1)