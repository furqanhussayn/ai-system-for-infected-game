from __future__ import annotations

from os import getenv


DEFAULT_PROVIDER = "gemini"
SUPPORTED_PROVIDERS = {"groq", "gemini"}


def normalize_provider(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in {"groq", "grok"}:
        return "groq"
    if raw in {"gemini", "google", "google-gemini"}:
        return "gemini"
    return DEFAULT_PROVIDER


def resolve_provider() -> str:
    """Resolve the active LLM provider from a single config variable."""
    return normalize_provider(getenv("MODEL_PROVIDER") or getenv("LLM_PROVIDER") or DEFAULT_PROVIDER)


MODEL_PROVIDER = resolve_provider()
LLM_PROVIDER = MODEL_PROVIDER
