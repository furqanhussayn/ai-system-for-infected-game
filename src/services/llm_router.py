from __future__ import annotations

from typing import Any

from src.core import config
from src.services import gemini_adapter
from src.services import llm_adapter
from src.services.groq_key_pool import (
    get_available_groq_keys,
    get_groq_key_slot,
    load_groq_keys,
    mark_key_failed,
    mark_key_rate_limited,
    mark_key_success,
)


_RETRYABLE_STAGES = {"rate_limited", "timeout", "provider_capacity", "server_error", "empty_response", "adapter_exception"}
_COOLDOWN_STAGES = {"invalid_api_key", "forbidden"}


def _failure_entry(*, key_id: str, stage: str, status_code: int | None) -> dict[str, object]:
    return {
        "keyId": key_id,
        "stage": stage,
        "statusCode": status_code,
    }


def _provider_entry(*, provider: str, model: str, stage: str, status_code: int | None = None, key_id: str = "") -> dict[str, object]:
    entry: dict[str, object] = {
        "provider": provider,
        "model": model,
        "stage": stage,
    }
    if key_id:
        entry["keyId"] = key_id
    if status_code is not None:
        entry["statusCode"] = status_code
    return entry


def _order_tokens() -> list[str]:
    order = list(getattr(config, "CHAT_PROVIDER_ORDER", ["gemini", "groq_key_1", "groq_key_2", "groq_key_3", "rules"]))
    normalized: list[str] = []
    for token in order:
        cleaned = str(token).strip().lower()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _provider_attempt_limit() -> int:
    return max(1, int(getattr(config, "LLM_MAX_PROVIDER_ATTEMPTS", 4) or 4))


def _select_key_slots() -> list:
    load_groq_keys()
    slots = get_available_groq_keys()
    if not config.LLM_GROQ_KEY_FAILOVER_ENABLED:
        return slots[:1]
    max_attempts = max(1, int(getattr(config, "LLM_GROQ_MAX_KEY_ATTEMPTS", 3) or 3))
    return slots[:max_attempts]


async def generate_for_chat(
    prompt_or_messages: object,
    *,
    model: str | None = None,
    purpose: str = "respond",
    max_output_tokens: int = 80,
    temperature: float = 0.7,
) -> llm_adapter.LLMResult:
    if not getattr(config, "LLM_PROVIDER_FAILOVER_ENABLED", True):
        order = _order_tokens()[:1]
    else:
        order = _order_tokens()

    failure_chain: list[dict[str, object]] = []
    attempt_count = 0
    last_result: llm_adapter.LLMResult | None = None
    attempt_limit = _provider_attempt_limit()

    groq_model = model or config.GROQ_CHAT_MODEL or config.GROQ_MODEL
    gemini_model = model or config.GEMINI_CHAT_MODEL or config.GEMINI_MODEL

    for token in order:
        if attempt_count >= attempt_limit:
            break

        if token == "rules":
            break

        if token == "gemini":
            gemini_status = gemini_adapter.get_gemini_status()
            if not gemini_status.get("configured") or gemini_status.get("cooldownActive"):
                failure_chain.append(_provider_entry(provider="gemini", model=str(gemini_model), stage="missing_api_key" if not gemini_status.get("configured") else "cooldown"))
                continue

            result = await gemini_adapter.generate_chat_response(
                prompt_or_messages,
                model=gemini_model,
                api_key=config.GEMINI_API_KEY.strip(),
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
            if not isinstance(result, llm_adapter.LLMResult):
                result = llm_adapter._coerce_public_call_result(result)
            result.provider = "gemini"
            result.model = str(result.model or gemini_model)
            attempt_count += 1
            result.attemptCount = attempt_count
            last_result = result

            if result.ok:
                result.failureChain = failure_chain + [_provider_entry(provider="gemini", model=result.model, stage="success", status_code=result.statusCode or 200)]
                return result

            failure_chain.append(_provider_entry(provider="gemini", model=result.model, stage=result.stage or "adapter_exception", status_code=result.statusCode))

            if result.stage == "model_unavailable" and config.GEMINI_BACKUP_CHAT_MODEL and config.GEMINI_BACKUP_CHAT_MODEL != result.model and attempt_count < attempt_limit:
                backup_result = await gemini_adapter.generate_chat_response(
                    prompt_or_messages,
                    model=config.GEMINI_BACKUP_CHAT_MODEL,
                    api_key=config.GEMINI_API_KEY.strip(),
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )
                if not isinstance(backup_result, llm_adapter.LLMResult):
                    backup_result = llm_adapter._coerce_public_call_result(backup_result)
                backup_result.provider = "gemini"
                backup_result.model = str(backup_result.model or config.GEMINI_BACKUP_CHAT_MODEL)
                attempt_count += 1
                backup_result.attemptCount = attempt_count
                last_result = backup_result
                if backup_result.ok:
                    backup_result.failureChain = failure_chain + [_provider_entry(provider="gemini", model=result.model, stage="model_unavailable"), _provider_entry(provider="gemini", model=backup_result.model, stage="success", status_code=backup_result.statusCode or 200)]
                    return backup_result
                failure_chain.append(_provider_entry(provider="gemini", model=backup_result.model, stage=backup_result.stage or "adapter_exception", status_code=backup_result.statusCode))
            continue

        if token in {"groq", "groq_key_1", "groq_key_2", "groq_key_3"}:
            if token == "groq":
                result = await generate_groq_with_key_failover(
                    prompt_or_messages,
                    model=groq_model,
                    purpose=purpose,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )
            else:
                slot = get_groq_key_slot(token)
                if slot is None or not slot.is_available:
                    failure_chain.append(_failure_entry(key_id=token, stage="cooldown", status_code=None))
                    continue
                result = await generate_groq_with_specific_key(
                    prompt_or_messages,
                    key_id=token,
                    model=groq_model,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )

            attempt_count += max(1, int(result.attemptCount or 1))
            result.attemptCount = attempt_count
            last_result = result
            if result.ok:
                result.failureChain = failure_chain + [_provider_entry(provider="groq", model=result.model or str(groq_model), key_id=result.keyId or token, stage="success", status_code=result.statusCode or 200)]
                return result
            failure_chain.append(
                {
                    "provider": "groq",
                    "model": str(result.model or groq_model),
                    "keyId": result.keyId or token,
                    "stage": result.stage or "adapter_exception",
                    "statusCode": result.statusCode,
                }
            )
            continue

    final_result = last_result or llm_adapter.LLMResult(
        ok=False,
        text="",
        provider="rules",
        model="",
        statusCode=None,
        errorType="all_providers_failed",
        errorMessage="All providers failed.",
        stage="all_providers_failed",
        rawPreview="",
        latencyMs=0,
        attemptCount=attempt_count,
        llmUsed=False,
        keyId="",
        failureChain=failure_chain,
    )
    final_result.ok = False
    final_result.provider = final_result.provider or "rules"
    final_result.stage = "all_providers_failed"
    final_result.errorType = "all_providers_failed"
    final_result.errorMessage = final_result.errorMessage or "All providers failed."
    final_result.failureChain = failure_chain
    final_result.attemptCount = attempt_count
    return final_result


async def generate_groq_with_key_failover(
    prompt_or_messages: object,
    *,
    model: str | None = None,
    purpose: str = "chat",
    max_output_tokens: int = 80,
    temperature: float = 0.7,
) -> llm_adapter.LLMResult:
    key_slots = _select_key_slots()
    actual_model = (model or config.GROQ_CHAT_MODEL or config.GROQ_MODEL).strip()
    if not key_slots:
        return llm_adapter.LLMResult(
            ok=False,
            text="",
            provider="groq",
            model=actual_model,
            statusCode=None,
            errorType="missing_api_key",
            errorMessage="No Groq API keys are configured.",
            stage="missing_api_key",
            rawPreview="",
            latencyMs=0,
            attemptCount=0,
            llmUsed=False,
            keyId="",
            failureChain=[],
        )

    failure_chain: list[dict[str, object]] = []
    attempt_count = 0
    last_failure: llm_adapter.LLMResult | None = None

    for slot in key_slots:
        attempt_count += 1
        result = await llm_adapter.generate_chat_response_result(
            prompt_or_messages,
            model=actual_model,
            api_key=slot.key_value,
            key_id=slot.key_id,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            max_retries=0,
            timeout_seconds=int(getattr(config, "LLM_TIMEOUT_SECONDS", 8)),
        )
        result.provider = "groq"
        result.model = actual_model
        result.keyId = slot.key_id
        result.attemptCount = attempt_count

        if result.ok:
            mark_key_success(slot.key_id)
            result.failureChain = failure_chain + [_failure_entry(key_id=slot.key_id, stage="success", status_code=result.statusCode or 200)]
            return result

        stage = str(result.stage or "adapter_exception")
        status_code = result.statusCode
        failure_chain.append(_failure_entry(key_id=slot.key_id, stage=stage, status_code=status_code))
        last_failure = result

        if stage == "rate_limited":
            mark_key_rate_limited(slot.key_id, int(getattr(config, "LLM_RATE_LIMIT_COOLDOWN_SECONDS", 600)))
        elif stage in _COOLDOWN_STAGES:
            mark_key_failed(slot.key_id, stage, int(getattr(config, "LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)))
        elif stage in _RETRYABLE_STAGES:
            mark_key_failed(slot.key_id, stage, int(getattr(config, "LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)))
        else:
            mark_key_failed(slot.key_id, stage, int(getattr(config, "LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)))

    final_result = last_failure or llm_adapter.LLMResult(
        ok=False,
        text="",
        provider="groq",
        model=actual_model,
        statusCode=None,
        errorType="adapter_exception",
        errorMessage="All Groq keys failed.",
        stage="all_groq_keys_failed",
        rawPreview="",
        latencyMs=0,
        attemptCount=attempt_count,
        llmUsed=False,
        keyId=key_slots[-1].key_id if key_slots else "",
        failureChain=failure_chain,
    )
    final_result.ok = False
    final_result.provider = "groq"
    final_result.model = actual_model
    final_result.keyId = key_slots[-1].key_id if key_slots else ""
    final_result.attemptCount = attempt_count
    final_result.failureChain = failure_chain
    if not final_result.errorMessage:
        final_result.errorMessage = "All Groq keys failed."
    if not final_result.stage:
        final_result.stage = "all_groq_keys_failed"
    return final_result


def get_groq_key_by_selection(selection: str | None) -> str | None:
    if not selection:
        return None
    cleaned = str(selection).strip().lower()
    if cleaned in {"1", "groq_key_1"}:
        return "groq_key_1"
    if cleaned in {"2", "groq_key_2"}:
        return "groq_key_2"
    if cleaned in {"3", "groq_key_3"}:
        return "groq_key_3"
    return None


async def generate_groq_with_specific_key(
    prompt_or_messages: object,
    *,
    key_id: str,
    model: str | None = None,
    max_output_tokens: int = 80,
    temperature: float = 0.7,
) -> llm_adapter.LLMResult:
    slot = get_groq_key_slot(key_id)
    actual_model = (model or config.GROQ_CHAT_MODEL or config.GROQ_MODEL).strip()
    if slot is None:
        return llm_adapter.LLMResult(
            ok=False,
            text="",
            provider="groq",
            model=actual_model,
            statusCode=None,
            errorType="missing_api_key",
            errorMessage="Requested Groq key is unavailable.",
            stage="missing_api_key",
            rawPreview="",
            latencyMs=0,
            attemptCount=0,
            llmUsed=False,
            keyId=key_id,
            failureChain=[],
        )

    result = await llm_adapter.generate_chat_response_result(
        prompt_or_messages,
        model=actual_model,
        api_key=slot.key_value,
        key_id=slot.key_id,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        max_retries=0,
        timeout_seconds=int(getattr(config, "LLM_TIMEOUT_SECONDS", 8)),
    )
    result.provider = "groq"
    result.model = actual_model
    result.keyId = slot.key_id
    result.attemptCount = 1
    if result.ok:
        mark_key_success(slot.key_id)
    elif result.stage == "rate_limited":
        mark_key_rate_limited(slot.key_id, int(getattr(config, "LLM_RATE_LIMIT_COOLDOWN_SECONDS", 600)))
    elif result.stage in _COOLDOWN_STAGES:
        mark_key_failed(slot.key_id, result.stage, int(getattr(config, "LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)))
    return result