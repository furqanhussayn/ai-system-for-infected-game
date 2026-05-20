from os import getenv
from pathlib import Path

from dotenv import load_dotenv

from src.core.model_choice import LLM_PROVIDER as MODEL_PROVIDER

_CONFIG_DIR = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _CONFIG_DIR.parent

load_dotenv(_WORKSPACE_ROOT / ".env")
load_dotenv(_CONFIG_DIR / ".env")


def _get_int(name: str, default: int) -> int:
	raw_value = getenv(name, str(default)).strip()
	try:
		return int(raw_value)
	except (TypeError, ValueError):
		return default


AI_MODE = getenv("AI_MODE", "rules").strip().lower()
LLM_PROVIDER = MODEL_PROVIDER
GROQ_API_KEY = getenv("GROQ_API_KEY", "").strip()
GROQ_API_KEY_2 = getenv("GROQ_API_KEY_2", "").strip()
GROQ_API_KEY_3 = getenv("GROQ_API_KEY_3", "").strip()
GEMINI_API_KEY = getenv("GEMINI_API_KEY", "").strip()
CHAT_PROVIDER_ORDER = [part.strip().lower() for part in getenv("CHAT_PROVIDER_ORDER", "gemini,groq_key_1,groq_key_2,groq_key_3,rules").split(",") if part.strip()]
GEMINI_CHAT_MODEL = getenv("GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite").strip()
GEMINI_BACKUP_CHAT_MODEL = getenv("GEMINI_BACKUP_CHAT_MODEL", "gemini-2.5-flash-lite").strip()
GROQ_MODEL = getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GEMINI_MODEL = getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
LLM_TIMEOUT_SECONDS = _get_int("LLM_TIMEOUT_SECONDS", 8)
LLM_MAX_RETRIES = _get_int("LLM_MAX_RETRIES", 1)
AI_CALL_MIN_INTERVAL = _get_int("AI_CALL_MIN_INTERVAL", 20)
FIREBASE_DATABASE_URL = getenv("FIREBASE_DATABASE_URL", "").strip()
FIREBASE_CONFIGURED = bool(FIREBASE_DATABASE_URL)

# Prompt budgeting and model selection
GROQ_CHAT_MODEL = getenv("GROQ_CHAT_MODEL", "llama-3.1-8b-instant").strip()
GROQ_DECISION_MODEL = getenv("GROQ_DECISION_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_VOTE_MODEL = getenv("GROQ_VOTE_MODEL", "llama-3.1-8b-instant").strip()
LLM_USE_70B_FOR_CHAT = getenv("LLM_USE_70B_FOR_CHAT", "false").strip().lower() in ("1", "true", "yes", "y")
LLM_RECENT_CHAT_LIMIT = _get_int("LLM_RECENT_CHAT_LIMIT", 6)
LLM_RELEVANT_CHAT_LIMIT = _get_int("LLM_RELEVANT_CHAT_LIMIT", 4)
LLM_MAX_PROMPT_CHARS = _get_int("LLM_MAX_PROMPT_CHARS", 2200)
LLM_MAX_OUTPUT_TOKENS = _get_int("LLM_MAX_OUTPUT_TOKENS", 80)
LLM_CHAT_MAX_BOTS_PER_EVENT = _get_int("LLM_CHAT_MAX_BOTS_PER_EVENT", 1)
LLM_PROMPT_MODE = getenv("LLM_PROMPT_MODE", "compact").strip()
LLM_TRACE_PROMPT_STATS = getenv("LLM_TRACE_PROMPT_STATS", "true").strip().lower() in ("1", "true", "yes", "y")
LLM_PROVIDER_FAILOVER_ENABLED = getenv("LLM_PROVIDER_FAILOVER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
LLM_MAX_PROVIDER_ATTEMPTS = _get_int("LLM_MAX_PROVIDER_ATTEMPTS", 4)
LLM_KEY_COOLDOWN_SECONDS = _get_int("LLM_KEY_COOLDOWN_SECONDS", 600)
LLM_GROQ_KEY_FAILOVER_ENABLED = getenv("LLM_GROQ_KEY_FAILOVER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")
LLM_GROQ_MAX_KEY_ATTEMPTS = _get_int("LLM_GROQ_MAX_KEY_ATTEMPTS", 3)
LLM_GROQ_KEY_COOLDOWN_SECONDS = _get_int("LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)
LLM_RATE_LIMIT_COOLDOWN_SECONDS = _get_int("LLM_RATE_LIMIT_COOLDOWN_SECONDS", 600)

# Cache and rate limit
LLM_ENABLE_CACHE = getenv("LLM_ENABLE_CACHE", "true").strip().lower() in ("1", "true", "yes", "y")
LLM_CACHE_TTL_SECONDS = _get_int("LLM_CACHE_TTL_SECONDS", 120)
