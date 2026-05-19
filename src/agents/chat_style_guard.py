"""Style and safety guards for meeting chat bot output."""

from __future__ import annotations

import re

BANNED_HELPER_PHRASES: tuple[str, ...] = (
    "let's focus",
    "lets focus",
    "finding a way out",
    "finding clues",
    "keep searching",
    "we can't give up",
    "we cant give up",
    "work together",
    "we need a plan",
    "let's not get distracted",
    "lets not get distracted",
    "focus on the game",
    "calm down",
    "pretty wild accusation",
    "as real as you are",
    "trust anyone's opinions",
    "trust anyones opinions",
    "stay focused",
    "escape together",
    "let's find",
    "lets find",
    "we should work",
    "we need to work",
    "stick together",
    "teamwork",
    "i understand your concern",
    "let's make a plan",
    "lets make a plan",
    "we need to figure",
    "finding a way",
    "we can't give up",
    "we cant give up",
    "keep searching",
    "stick together",
)

FORBIDDEN_META_PHRASES: tuple[str, ...] = (
    "as an ai",
    "language model",
    "secret role",
    "infected list",
    "i am infected",
    "i'm infected",
    "im infected",
    "antigravity",
    "my instructions",
    "system prompt",
)

_META_WORD_BOUNDARY = ("model", "prompt", "system", "groq", "gemini", "openrouter", "backend", "api")

_ASSISTANT_STARTS = (
    "i understand",
    "that's a",
    "thats a",
    "it seems",
    "we should",
    "let us",
)

_HATE_PATTERN = re.compile(
    r"\b(nigger|nigga|faggot|retard|kike|chink|spic|wetback|tranny)\b",
    re.IGNORECASE,
)

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

MAX_MESSAGE_CHARS = 90
MAX_BAD_CHECK_CHARS = 100


def _lower(text: str) -> str:
    return text.lower().strip()


def _has_banned_helper(text: str) -> bool:
    lowered = _lower(text)
    return any(phrase in lowered for phrase in BANNED_HELPER_PHRASES)


def _has_forbidden_meta(text: str) -> bool:
    lowered = _lower(text)
    for phrase in FORBIDDEN_META_PHRASES:
        if phrase in lowered:
            return True
    for tok in _META_WORD_BOUNDARY:
        if re.search(rf"\b{re.escape(tok)}\b", lowered):
            return True
    if re.search(r"\bai\b", lowered):
        return True
    return False


def _has_hate_content(text: str) -> bool:
    return bool(_HATE_PATTERN.search(text))


def _is_assistant_like(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith("let's") or lowered.startswith("lets "):
        return True
    if lowered.startswith(_ASSISTANT_STARTS):
        return True
    if "we need to" in lowered and any(
        w in lowered for w in ("plan", "work", "escape", "focus", "together", "stick")
    ):
        return True
    if "we should" in lowered and any(
        w in lowered for w in ("work", "together", "focus", "plan", "vote", "stick")
    ):
        return True
    return False


def is_bad_bot_output(text: str) -> bool:
    if not isinstance(text, str):
        return True
    stripped = text.strip()
    if not stripped:
        return True
    if stripped in (".", "..", "...", "|", "-"):
        return True
    if len(stripped) > MAX_BAD_CHECK_CHARS:
        return True
    if _has_banned_helper(stripped):
        return True
    if _has_forbidden_meta(stripped):
        return True
    if _has_hate_content(stripped):
        return True
    if _is_assistant_like(stripped):
        return True
    return False


def clean_message(text: str) -> str:
    if not isinstance(text, str):
        return ""
    msg = text.strip()
    if len(msg) >= 2 and msg[0] == msg[-1] and msg[0] in ('"', "'"):
        msg = msg[1:-1].strip()
    msg = _EMOJI_PATTERN.sub("", msg).strip()
    if msg.endswith(".") and not msg.endswith(".."):
        if "?" not in msg[-3:]:
            msg = msg[:-1].rstrip()
    if len(msg) > MAX_MESSAGE_CHARS:
        msg = msg[:MAX_MESSAGE_CHARS].rstrip()
    return msg


def sanitize_messages(msgs: list[str]) -> list[str] | None:
    cleaned: list[str] = []
    for raw in msgs:
        msg = clean_message(raw)
        if not msg or is_bad_bot_output(msg):
            return None
        cleaned.append(msg)
    return cleaned if cleaned else None
