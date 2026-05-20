"""Style and safety guards for meeting chat bot output."""

from __future__ import annotations

import re
import random
from typing import Any

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

_FILLER_WORDS = {
    "bro",
    "nah",
    "yeah",
    "ok",
    "okay",
    "fr",
    "tbh",
    "ngl",
    "like",
    "um",
    "uh",
    "yo",
    "hey",
    "honestly",
    "literally",
    "basically",
    "just",
    "really",
    "actually",
    "maybe",
    "kinda",
    "kind",
    "thats",
    "its",
    "u",
    "ur",
    "you",
    "your",
    "do",
    "did",
    "does",
    "have",
    "has",
    "had",
    "is",
    "are",
    "was",
    "were",
    "to",
    "too",
    "of",
    "on",
    "in",
    "at",
    "for",
    "with",
    "and",
    "or",
    "the",
    "a",
    "an",
    "i",
    "im",
    "ive",
}

_PROOF_WORDS = {"proof", "evidence", "explain", "why", "where", "show"}
_WEIRD_WORDS = {"weird", "sus", "odd", "strange", "off", "bizarre"}
_CONFUSED_WORDS = {"wait", "what", "huh", "lost", "confused", "why"}
_DENIAL_WORDS = {"no", "not", "never", "didnt", "didn", "wasnt", "wasn"}

_TOKEN_RE = re.compile(r"[a-z0-9']+")

_INTENT_VARIETY_POOLS: dict[str, list[str]] = {
    "answer_question": [
        "idk why u said it like that",
        "that was just random",
        "kinda sus way to open meeting",
        "are u trying to bait reactions",
        "what are u even asking",
    ],
    "agree": [
        "same thought tbh",
        "yeah but dont rush vote",
        "i get what u mean",
        "it was odd ngl",
        "not enough to vote tho",
    ],
    "ask_question": [
        "what exactly are u asking",
        "who are u talking about",
        "why say it like that",
        "does that matter",
        "what do u want us to say",
    ],
    "confused": [
        "wait im lost",
        "i dont get what u mean",
        "why are we talking about this",
        "huh",
        "what happened",
    ],
    "deflect": [
        "player 1 is acting too casual rn",
        "this feels like bait",
        "why start meeting like that",
        "someone is trying to waste time",
        "id rather talk routes",
    ],
    "accuse_other": [
        "player 1 is dodging real questions",
        "that opener was weird from player 1",
        "player 3 has been quiet tho",
        "someone is trying to distract us",
        "this feels like a cover",
    ],
    "defend_self": [
        "nah that was not me",
        "i was nowhere near that",
        "that read is off",
        "i didnt do anything weird",
        "youre stretching that hard",
    ],
    "deny": [
        "nah that was not me",
        "i was nowhere near that",
        "that read is off",
        "i didnt do anything weird",
        "youre stretching that hard",
    ],
    "third_party_opinion": [
        "this opener was weird",
        "not enough proof yet",
        "that feels off",
        "someone is forcing the angle",
        "i wouldnt vote off that alone",
    ],
    "pile_on": [
        "yeah that was weird",
        "still not buying that",
        "that sounded like a dodge",
        "someone is acting off",
        "too convenient tbh",
    ],
    "calm_down_short": [
        "slow down",
        "hold on",
        "wait a sec",
        "easy",
        "dont rush it",
    ],
    "disagree": [
        "not really",
        "nah i dont see it",
        "that doesnt follow",
        "im not sold on that",
        "i disagree",
    ],
    "stay_out": [
        "idk yet",
        "not enough proof",
        "i didnt see it",
        "hard to say rn",
        "im not sure",
    ],
}


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
            # skip any single invalid message but continue trying others
            continue
        cleaned.append(msg)
    return cleaned if cleaned else None


def _stem_token(token: str) -> str:
    if len(token) <= 3:
        return token
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _message_tokens(text: str) -> list[str]:
    cleaned = clean_message(text).lower().replace("'", "")
    tokens: list[str] = []
    for raw_token in _TOKEN_RE.findall(cleaned):
        token = raw_token.strip()
        if not token or token in _FILLER_WORDS:
            continue
        if token == "u":
            token = "you"
        token = _stem_token(token)
        if token and token not in _FILLER_WORDS:
            tokens.append(token)
    return tokens


def normalize_message_key(text: str) -> str:
    tokens = _message_tokens(text)
    if not tokens:
        return clean_message(text).lower().strip()

    token_set = set(tokens)
    if token_set & _PROOF_WORDS:
        return "proof_question"
    if token_set & _WEIRD_WORDS:
        return "weird_concern"
    if token_set & _CONFUSED_WORDS:
        return "confused"
    if token_set & _DENIAL_WORDS:
        return "denial"

    return " ".join(tokens[:8])


def message_opening_key(text: str) -> str:
    tokens = _message_tokens(text)
    if not tokens:
        return ""
    return " ".join(tokens[:2])


def _is_near_duplicate_tokens(candidate_tokens: list[str], other_tokens: list[str]) -> bool:
    if not candidate_tokens or not other_tokens:
        return False

    candidate_set = set(candidate_tokens)
    other_set = set(other_tokens)
    if not candidate_set or not other_set:
        return False

    if candidate_set == other_set:
        return True

    overlap = candidate_set & other_set
    if not overlap:
        return False

    if "proof" in candidate_set or "proof" in other_set:
        return True

    if len(candidate_set) <= 3 or len(other_set) <= 3:
        return len(overlap) >= 1

    overlap_ratio = len(overlap) / float(min(len(candidate_set), len(other_set)))
    return len(overlap) >= 2 and overlap_ratio >= 0.66


def is_duplicate_message(
    candidate: str,
    seen_messages: list[str] | None = None,
    *,
    seen_keys: set[str] | None = None,
    seen_openers: set[str] | None = None,
) -> bool:
    candidate_clean = clean_message(candidate)
    if not candidate_clean:
        return True

    candidate_key = normalize_message_key(candidate_clean)
    candidate_opener = message_opening_key(candidate_clean)
    candidate_tokens = _message_tokens(candidate_clean)

    if seen_keys and candidate_key in seen_keys:
        return True
    if seen_openers and candidate_opener and candidate_opener in seen_openers:
        return True

    for seen in seen_messages or []:
        seen_clean = clean_message(seen)
        if not seen_clean:
            continue
        if candidate_clean.lower() == seen_clean.lower():
            return True

        seen_key = normalize_message_key(seen_clean)
        if candidate_key == seen_key:
            return True

        if _is_near_duplicate_tokens(candidate_tokens, _message_tokens(seen_clean)):
            return True

    return False


def _replacement_pool_for_intent(intent: str) -> list[str]:
    return list(_INTENT_VARIETY_POOLS.get(intent, _INTENT_VARIETY_POOLS["third_party_opinion"]))


def pick_diverse_replacement(
    *,
    intent: str,
    seen_messages: list[str] | None = None,
    seen_keys: set[str] | None = None,
    seen_openers: set[str] | None = None,
    recent_messages: list[str] | None = None,
    latest_human_message: str = "",
) -> str | None:
    seen_messages = list(seen_messages or [])
    recent_messages = list(recent_messages or [])
    candidate_pool = _replacement_pool_for_intent(intent)
    random.shuffle(candidate_pool)

    blocked_messages = seen_messages + recent_messages
    if latest_human_message:
        blocked_messages.append(latest_human_message)

    blocked_keys = set(seen_keys or set())
    for text in blocked_messages:
        key = normalize_message_key(text)
        if key:
            blocked_keys.add(key)

    blocked_openers = set(seen_openers or set())
    for candidate in candidate_pool:
        candidate_clean = clean_message(candidate)
        if not candidate_clean:
            continue
        candidate_key = normalize_message_key(candidate_clean)
        candidate_opener = message_opening_key(candidate_clean)
        if candidate_key in blocked_keys or (candidate_opener and candidate_opener in blocked_openers):
            continue
        if is_duplicate_message(
            candidate_clean,
            blocked_messages,
            seen_keys=blocked_keys,
            seen_openers=blocked_openers,
        ):
            continue
        return candidate_clean

    return None


def dedupe_and_replace_messages(
    messages: list[str],
    *,
    event_context: dict[str, Any] | None = None,
    intent: str = "third_party_opinion",
) -> tuple[list[str], dict[str, Any]]:
    context = event_context or {}
    used_messages = list(context.get("usedMessages", []))
    used_message_keys = set(context.get("usedMessageKeys", []))
    used_openers = set(context.get("usedOpeners", []))
    recent_chat_texts = list(context.get("recentChatTexts", []))
    latest_human_message = str(context.get("latestHumanMessage", "") or "")

    filtered: list[str] = []
    duplicate_filtered_count = 0
    duplicate_replaced_count = 0

    for raw_message in messages:
        candidate = clean_message(raw_message)
        if not candidate or is_bad_bot_output(candidate):
            continue

        candidate_key = normalize_message_key(candidate)
        candidate_opener = message_opening_key(candidate)

        if is_duplicate_message(
            candidate,
            used_messages + recent_chat_texts + ([latest_human_message] if latest_human_message else []),
            seen_keys=used_message_keys,
            seen_openers=used_openers,
        ):
            duplicate_filtered_count += 1
            replacement = pick_diverse_replacement(
                intent=intent,
                seen_messages=used_messages + filtered,
                seen_keys=used_message_keys,
                seen_openers=used_openers,
                recent_messages=recent_chat_texts,
                latest_human_message=latest_human_message,
            )
            if replacement:
                candidate = replacement
                candidate_key = normalize_message_key(candidate)
                candidate_opener = message_opening_key(candidate)
                duplicate_replaced_count += 1
            else:
                continue

        if candidate_key in used_message_keys or (candidate_opener and candidate_opener in used_openers):
            continue

        filtered.append(candidate)
        used_messages.append(candidate)
        if candidate_key:
            used_message_keys.add(candidate_key)
        if candidate_opener:
            used_openers.add(candidate_opener)

    stats = {
        "duplicateFilteredCount": duplicate_filtered_count,
        "duplicateReplacedCount": duplicate_replaced_count,
        "usedMessageKeys": sorted(used_message_keys),
        "diversityApplied": bool(duplicate_filtered_count or duplicate_replaced_count),
    }
    return filtered, stats
