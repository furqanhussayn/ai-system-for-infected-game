from fastapi import APIRouter

from src.core import config

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
async def llm_status():
    return {
        "aiMode": config.AI_MODE,
        "agentDecisionEnabled": config.AI_MODE == "agent",
        "provider": config.LLM_PROVIDER,
        "hasGroqKey": bool(config.GROQ_API_KEY),
        "hasGeminiKey": bool(getattr(config, "GEMINI_API_KEY", "")),
    }