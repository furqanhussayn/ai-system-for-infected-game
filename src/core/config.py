from os import getenv
from pathlib import Path

from dotenv import load_dotenv

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
LLM_PROVIDER = getenv("LLM_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = getenv("GEMINI_API_KEY", "").strip()
GROQ_MODEL = getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GEMINI_MODEL = getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
LLM_TIMEOUT_SECONDS = _get_int("LLM_TIMEOUT_SECONDS", 8)
AI_CALL_MIN_INTERVAL = _get_int("AI_CALL_MIN_INTERVAL", 20)
FIREBASE_DATABASE_URL = getenv("FIREBASE_DATABASE_URL", "").strip()
FIREBASE_CONFIGURED = bool(FIREBASE_DATABASE_URL)
