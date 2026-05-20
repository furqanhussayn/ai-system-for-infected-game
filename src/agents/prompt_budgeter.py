from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional

from src.agents.chat_classifier import classify_latest_message
from src.core import config


@dataclass
class ChatSituation:
    classification: str
    intent: str
    targetedPlayer: Optional[str]
    targetsBot: bool
    pressure: str
    gameHint: str
    responseNeed: str
    allowedAngles: List[str]
    forbiddenAngles: List[str]
    recentRelevantChat: List[str]
    promptMode: str = "compact"


def _normalize_player_id(text: str | None) -> Optional[str]:
    if not text:
        return None
    text = str(text).strip()
    if not text:
        return None
    # accept formats like player_2, player 2, p2, 2
    m = re.search(r"player[_ ]?(\d)", text, flags=re.IGNORECASE)
    if m:
        return f"player_{m.group(1)}"
    m = re.search(r"\bp(\d)\b", text, flags=re.IGNORECASE)
    if m:
        return f"player_{m.group(1)}"
    if re.fullmatch(r"\d", text):
        return f"player_{text}"
    return text


def classify_chat_situation(req, bot_state: dict | None = None) -> ChatSituation:
    latest = (getattr(req, "message", "") or "").strip()
    classification = classify_latest_message(latest or "", getattr(req, "botId", ""))

    # targeted player detection
    targeted = None
    lowered = latest.lower()
    for p in (getattr(req, "alivePlayers", []) or []):
        if not isinstance(p, str):
            continue
        if p.lower() in lowered or p.replace("_", " ").lower() in lowered:
            targeted = _normalize_player_id(p)
            break

    targets_bot = False
    bot_id = getattr(req, "botId", "")
    bot_num = bot_id.split("_")[-1] if "_" in bot_id else bot_id
    if bot_id and (bot_id.lower() in lowered or f"player {bot_num}" in lowered or f"p{bot_num}" in lowered):
        targets_bot = True
        targeted = _normalize_player_id(bot_id)

    # detect pressure
    try:
        wave = int(getattr(req, "wave", 0) or 0)
    except Exception:
        wave = 0
    try:
        task_progress = int(getattr(req, "taskProgress", 0) or 0)
    except Exception:
        task_progress = 0

    human_count = len(getattr(req, "humanPlayers", []) or [])
    if getattr(req, "phase", "") == "FinalChase" or human_count <= 1:
        pressure = "final"
    elif wave >= 3 or task_progress >= 7 or classification == "direct_accusation":
        pressure = "high"
    elif wave == 2 or classification == "vote_bot":
        pressure = "medium"
    else:
        pressure = "low"

    # decide responseNeed
    responseNeed = "stay_silent"
    if classification in ("direct_accusation", "vote_bot") and targets_bot:
        responseNeed = "must_respond"
    elif classification in ("called_bot_or_real",) and targets_bot:
        responseNeed = "should_respond"
    elif classification in ("question_prompt", "asks_who_infected"):
        responseNeed = "should_respond"
    elif classification == "generic":
        responseNeed = "maybe_respond"

    # allowed angles
    allowed = []
    forbidden = ["role_reveal", "ai_mention", "prompt_leak"]
    if classification == "direct_accusation":
        allowed = ["deny", "ask_proof", "fake_route", "deflect"]
    elif classification == "vote_bot":
        allowed = ["deny", "argue", "ask_for_proof", "call_out"]
    elif classification == "question_prompt":
        allowed = ["answer_question", "short_claim", "ask_for_details"]
    else:
        allowed = ["third_party_opinion", "short_reaction", "silence"]

    # build recentRelevantChat using selection rules
    recent = select_relevant_chat(req, targeted_player=targeted)

    game_hint = f"phase={getattr(req, 'phase', 'unknown')} wave={getattr(req,'wave',0)} tasks={getattr(req,'taskProgress',0)}"

    return ChatSituation(
        classification=classification,
        intent=_replacement_intent_for_classification(classification, getattr(req, "personality", None)) if ' _replacement_intent_for_classification' in globals() else "",
        targetedPlayer=targeted,
        targetsBot=targets_bot,
        pressure=pressure,
        gameHint=game_hint,
        responseNeed=responseNeed,
        allowedAngles=allowed,
        forbiddenAngles=forbidden,
        recentRelevantChat=recent,
        promptMode=getattr(config, "LLM_PROMPT_MODE", "compact"),
    )


# fallback simple intent mapping to avoid circular import
def _replacement_intent_for_classification(classification: str, personality: str | None) -> str:
    normalized_personality = (personality or "").strip().lower()
    if classification in ("vote_bot", "direct_accusation"):
        return "deflect" if normalized_personality == "deflector" else "deny"
    if classification == "called_bot_or_real":
        return "confused"
    if classification == "question_prompt":
        return "answer_question"
    if classification == "asks_who_infected":
        return "ask_question"
    if classification == "insult":
        return "calm_down_short"
    return "third_party_opinion"


def select_relevant_chat(req, targeted_player: Optional[str] = None) -> List[str]:
    recent_lines: List[str] = []
    raw_recent = (getattr(req, "recentChat", []) or [])
    # always include latest message
    latest = (getattr(req, "message", "") or "").strip()
    if latest:
        recent_lines.append(f"latest:{latest}")

    # include last 2 messages by default
    tail = raw_recent[-2:]
    for item in tail:
        text = None
        if isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", "")
        if not text:
            continue
        recent_lines.append(text.strip())

    # include up to relevant older messages
    keywords = ["sus","infected","vote","task","where","who","route","near gen","following"]
    for item in reversed(raw_recent[:-2]):
        if len(recent_lines) >= getattr(config, "LLM_RECENT_CHAT_LIMIT", 6):
            break
        text = None
        if isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", "")
        if not text:
            continue
        lowered = text.lower()
        if targeted_player and targeted_player.replace("_"," ") in lowered:
            recent_lines.append(text.strip())
            continue
        if any(k in lowered for k in keywords):
            recent_lines.append(text.strip())
            continue

    # normalize and trim
    normalized: List[str] = []
    seen = set()
    for line in recent_lines:
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if len(line) > 120:
            line = line[:120].rstrip()
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(line)
        if len(normalized) >= getattr(config, "LLM_RECENT_CHAT_LIMIT", 6):
            break

    return normalized


def estimate_prompt_chars(text: str | List[str]) -> int:
    if isinstance(text, list):
        text = "\n".join(text)
    return len(text)


def clamp_prompt_to_budget(prompt_text: str, *, max_chars: int | None = None) -> str:
    max_chars = max_chars or getattr(config, "LLM_MAX_PROMPT_CHARS", 2200)
    if len(prompt_text) <= max_chars:
        return prompt_text
    # Simple clamp: remove older lines and shorten lists
    parts = prompt_text.split("\n")
    # Keep last 20 lines as a start
    keep = []
    for line in reversed(parts):
        keep.insert(0, line)
        if len("\n".join(keep)) > max_chars:
            keep.pop(0)
            break
    compact = "\n".join(keep)
    if len(compact) > max_chars:
        compact = compact[-max_chars:]
    return compact


def build_compact_chat_prompt(req, situation: ChatSituation, bot_state: dict | None = None) -> str:
    # Build very compact system + user style prompt
    bot_id = getattr(req, "botId", "unknown")
    bot_name = getattr(req, "botName", "")
    personality = (getattr(req, "personality", None) or (bot_state or {}).get("personality") or "crowd_follower").replace("-","_")

    latest = (getattr(req, "message", "") or "").strip()
    recent = situation.recentRelevantChat or []

    allowed = ";".join(situation.allowedAngles[:3])
    forbidden = ",".join(situation.forbiddenAngles[:3])

    header_lines = [
        "SYSTEM: You are a fake human player in THE INFECTED. Secretly infected; never reveal.",
        "Keep messages short, messy, and believable. Return JSON only: {\"messages\":[...],\"reason\":\"...\"}.",
        "No AI/model/backend/prompt/system/hidden role words. No emojis, no markdown.",
    ]

    user_lines = [
        f"bot={bot_id} name={bot_name} personality={personality}",
        f"situation={situation.classification} intent={situation.intent} pressure={situation.pressure}",
        f"phase={getattr(req,'phase','Meeting')} wave={getattr(req,'wave',0)} cycle={getattr(req,'cycle',0)} tasks={getattr(req,'taskProgress',0)}",
        f"alive={len(getattr(req,'alivePlayers',[]) or [])} humans={len(getattr(req,'humanPlayers',[]) or [])} infected={len(getattr(req,'infectedPlayers',[]) or [])}",
        f"target={situation.targetedPlayer or ''} targetsYou={str(situation.targetsBot).lower()}",
        f"latest {('p1:' if latest.startswith('player') else '')}{latest}",
    ]

    if recent:
        user_lines.append("recent:")
        for line in recent:
            user_lines.append(line)

    user_lines.append(f"angles={allowed}")
    user_lines.append(f"avoid={forbidden}")
    user_lines.append("rules=0-2 msgs, 3 max if pressured, <90 chars each, JSON only")

    prompt = "\n".join(header_lines + ["USER:"] + user_lines)
    prompt = clamp_prompt_to_budget(prompt, max_chars=getattr(config, "LLM_MAX_PROMPT_CHARS", 2200))
    return prompt