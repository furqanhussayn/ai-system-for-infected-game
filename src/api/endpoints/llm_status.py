from fastapi import APIRouter, Query

from src.core import config
from src.services.gemini_adapter import generate_chat_response as generate_gemini_chat_response, get_gemini_status
from src.services.groq_key_pool import get_groq_key_slot, get_key_pool_status
from src.services.llm_router import generate_for_chat, generate_groq_with_specific_key, get_groq_key_by_selection

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
async def llm_status():
    gemini_status = get_gemini_status()
    pool_status = get_key_pool_status()
    chat_order = list(getattr(config, "CHAT_PROVIDER_ORDER", ["gemini", "groq_key_1", "groq_key_2", "groq_key_3", "rules"]))
    groq_payload = {
        "configured": bool(pool_status.get("keyCount", 0)),
        "model": config.GROQ_CHAT_MODEL,
        "keyCount": pool_status.get("keyCount", 0),
        "availableKeys": pool_status.get("availableKeys", 0),
        "cooldownKeys": pool_status.get("cooldownKeys", 0),
        "keys": [
            {
                "keyId": item.get("keyId", ""),
                "available": bool(item.get("available", False)),
                "lastError": item.get("lastError", ""),
            }
            for item in pool_status.get("keys", [])
        ],
    }
    return {
        "aiMode": config.AI_MODE,
        "agentDecisionEnabled": config.AI_MODE == "agent",
        "chatProviderOrder": chat_order,
        "provider": "gemini" if gemini_status.get("configured") else "groq",
        "model": gemini_status.get("model") if gemini_status.get("configured") else config.GROQ_CHAT_MODEL,
        "hasGroqKey": bool(pool_status.get("keyCount", 0)),
        "groqKeyFailoverEnabled": bool(getattr(config, "LLM_GROQ_KEY_FAILOVER_ENABLED", True)),
        "groq": groq_payload,
        "groqKeyPool": pool_status,
        "gemini": gemini_status,
        "hasGeminiKey": bool(getattr(config, "GEMINI_API_KEY", "")),
        "fallback": "rules",
        "timeoutSeconds": config.LLM_TIMEOUT_SECONDS,
        "maxOutputTokens": getattr(config, "LLM_MAX_OUTPUT_TOKENS", 80),
        "maxRetries": getattr(config, "LLM_MAX_RETRIES", 1),
    }


@router.get("/ping")
async def llm_ping(provider: str | None = Query(default=None), key: str | None = Query(default=None)):
    provider_name = str(provider or "").strip().lower()
    if not provider_name:
        result = await generate_for_chat("ok", model=None, purpose="ping", max_output_tokens=1, temperature=0.0)
    elif provider_name == "gemini":
        result = await generate_gemini_chat_response("ok", model=config.GEMINI_CHAT_MODEL, api_key=config.GEMINI_API_KEY, max_output_tokens=1, temperature=0.0)
    elif provider_name == "groq":
        key_id = get_groq_key_by_selection(key) or "groq_key_1"
        key_slot = get_groq_key_slot(key_id)
        if key_slot is None:
            return {
                "ok": False,
                "provider": "groq",
                "model": config.GROQ_CHAT_MODEL,
                "keyId": key_id,
                "stage": "missing_api_key",
                "statusCode": None,
                "latencyMs": 0,
                "errorMessage": "requested key unavailable",
            }
        result = await generate_groq_with_specific_key("ok", key_id=key_slot.key_id, model=config.GROQ_CHAT_MODEL, max_output_tokens=1, temperature=0.0)
    else:
        return {
            "ok": False,
            "provider": provider_name,
            "model": "",
            "keyId": "",
            "stage": "missing_api_key",
            "statusCode": None,
            "latencyMs": 0,
            "errorMessage": "requested provider unavailable",
        }
    return {
        "ok": bool(result.ok),
        "provider": result.provider,
        "model": result.model,
        "keyId": result.keyId,
        "llmUsed": bool(result.llmUsed),
        "statusCode": result.statusCode,
        "latencyMs": result.latencyMs,
        "stage": result.stage,
        "errorType": result.errorType,
        "errorMessage": result.errorMessage,
        "failureChain": result.failureChain,
    }