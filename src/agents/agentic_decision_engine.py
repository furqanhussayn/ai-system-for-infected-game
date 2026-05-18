from __future__ import annotations

import json
import re
from typing import Any

from src.core import config
from src.core.state import get_bot_state
from src.models.schemas import DecideRequest, RespondRequest, VoteRequest
from src.services import llm_adapter

ALLOWED_BEHAVIOR_MODES = {
    "stealth_fake_task",
    "stalk",
    "aggressive_chase",
    "final_hunt",
}

FORBIDDEN_CHAT_PHRASES = [
    "ai",
    "prompt",
    "system",
    "groq",
    "gemini",
    "antigravity",
    "secret role",
]


def _ai_mode_enabled() -> bool:
    return config.AI_MODE == "agent"


def _llm_ready() -> bool:
    return bool(config.GROQ_API_KEY.strip())


def _normalize_text(value: Any) -> str:
    return str(value).strip()


def _load_json(text: str | None) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _has_forbidden_chat_content(text: str) -> bool:
    lowered = text.lower()
    for phrase in FORBIDDEN_CHAT_PHRASES:
        if " " in phrase:
            if phrase in lowered:
                return True
        elif re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return True
    return False


def _valid_target_player(req: DecideRequest, target_player: Any) -> str | None:
    if target_player is None:
        return None
    if not isinstance(target_player, str):
        return None
    target_player = target_player.strip()
    if not target_player:
        return None
    valid_players = {player for player in req.humanPlayers if isinstance(player, str)}
    if target_player not in valid_players:
        return None
    if target_player == req.botId:
        return None
    return target_player


def _build_decide_prompt(req: DecideRequest, bot_state: dict[str, Any]) -> str:
    return (
        "Return strict JSON only. No markdown. No code fences. No explanation outside the JSON object.\n"
        "Choose one behaviorMode from: stealth_fake_task, stalk, aggressive_chase, final_hunt.\n"
        "If behaviorMode is final_hunt, only use it when exactly one human remains.\n"
        "targetPlayer must be a valid human or null.\n"
        "shouldChase should be true only for aggressive_chase or final_hunt.\n\n"
        f"matchId: {req.matchId}\n"
        f"botId: {req.botId}\n"
        f"phase: {req.phase}\n"
        f"wave: {req.wave}\n"
        f"infectedPlayers: {req.infectedPlayers}\n"
        f"humanPlayers: {req.humanPlayers}\n"
        f"nearestHuman: {req.nearestHuman}\n"
        f"botRoom: {req.botRoom or bot_state.get('botRoom')}\n"
    )


def _build_chat_prompt(req: RespondRequest, bot_state: dict[str, Any]) -> str:
    recent_chat = []
    for item in req.recentChat[-6:]:
        sender = _normalize_text(item.get("sender", "unknown"))
        text = _normalize_text(item.get("text", ""))
        recent_chat.append(f"- {sender}: {text}")

    chat_block = "\n".join(recent_chat) if recent_chat else "- no recent chat"
    return (
        "Return strict JSON only. No markdown, no explanation.\n"
        "Schema: {\"messages\": [\"short message\"], \"reason\": \"short reason\"}.\n"
        "Messages must be 1 to 2 items, each 160 chars max, and must not mention AI, prompt, system, Groq, Gemini, Antigravity, or secret role.\n"
        "If accused, deny or deflect naturally.\n\n"
        f"botId: {req.botId}\n"
        f"message: {req.message.strip()}\n"
        f"personality: {bot_state.get('personality', 'quiet')}\n"
        f"knownRoom: {bot_state.get('botRoom') or 'unknown'}\n"
        f"recentChat:\n{chat_block}\n"
    )


def _build_vote_prompt(req: VoteRequest, bot_state: dict[str, Any]) -> str:
    return (
        "Return strict JSON only. No markdown, no explanation.\n"
        "Schema: {\"voteTarget\": \"player_x\", \"reason\": \"short reason\"}.\n"
        "voteTarget must be a living player, not the bot, and not a known infected player.\n\n"
        f"botId: {req.botId}\n"
        f"alivePlayers: {req.alivePlayers}\n"
        f"infectedPlayers: {req.infectedPlayers}\n"
        f"recentChat: {req.recentChat}\n"
        f"botRoom: {bot_state.get('botRoom') or 'unknown'}\n"
    )


def _should_chase_for_mode(mode: str) -> bool:
    return mode in {"aggressive_chase", "final_hunt"}


async def decide_behavior_with_agent(request: DecideRequest) -> dict[str, Any] | None:
    if not _ai_mode_enabled() or not _llm_ready():
        return None

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    raw_text = await llm_adapter.generate_chat_response(_build_decide_prompt(request, bot_state))
    payload = _load_json(raw_text)
    if not payload:
        return None

    behavior_mode = payload.get("behaviorMode")
    if behavior_mode not in ALLOWED_BEHAVIOR_MODES:
        return None

    target_player = _valid_target_player(request, payload.get("targetPlayer"))
    if payload.get("targetPlayer") is not None and target_player is None:
        return None

    if behavior_mode == "final_hunt" and len(request.humanPlayers) != 1:
        return None

    should_chase = payload.get("shouldChase")
    if not isinstance(should_chase, bool) or should_chase != _should_chase_for_mode(behavior_mode):
        return None

    target_room = payload.get("targetRoom")
    if target_room is not None and not isinstance(target_room, str):
        return None
    target_room = target_room.strip() if isinstance(target_room, str) else None
    if target_room == "":
        target_room = None

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None

    return {
        "behaviorMode": behavior_mode,
        "targetPlayer": target_player,
        "targetRoom": target_room,
        "shouldChase": should_chase,
        "reason": reason.strip(),
    }


async def validate_decide_behavior_with_agent(request: DecideRequest) -> tuple[dict[str, Any] | None, str | None]:
    if not _ai_mode_enabled():
        return None, None
    if not _llm_ready():
        return None, "missing_llm_key"

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    raw_text = await llm_adapter.generate_chat_response(_build_decide_prompt(request, bot_state))
    payload = _load_json(raw_text)
    if not payload:
        return None, "invalid_json"

    behavior_mode = payload.get("behaviorMode")
    if behavior_mode not in ALLOWED_BEHAVIOR_MODES:
        return None, f"invalid behaviorMode: {behavior_mode!r}"

    target_player_raw = payload.get("targetPlayer")
    target_player = _valid_target_player(request, target_player_raw)
    if target_player_raw is not None and target_player is None:
        return None, f"invalid targetPlayer: {target_player_raw!r}"

    if behavior_mode == "final_hunt" and len(request.humanPlayers) != 1:
        return None, "final_hunt only allowed when one human remains"

    should_chase = payload.get("shouldChase")
    if not isinstance(should_chase, bool):
        return None, "shouldChase must be boolean"
    if should_chase != _should_chase_for_mode(behavior_mode):
        return None, f"shouldChase mismatch for {behavior_mode}"

    target_room = payload.get("targetRoom")
    if target_room is not None and not isinstance(target_room, str):
        return None, "targetRoom must be string or null"
    target_room = target_room.strip() if isinstance(target_room, str) else None
    if target_room == "":
        target_room = None

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None, "reason must be a non-empty string"

    return {
        "behaviorMode": behavior_mode,
        "targetPlayer": target_player,
        "targetRoom": target_room,
        "shouldChase": should_chase,
        "reason": reason.strip(),
    }, None


async def generate_chat_with_agent(request: RespondRequest) -> dict[str, Any] | None:
    if not _ai_mode_enabled() or not _llm_ready():
        return None

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    raw_text = await llm_adapter.generate_chat_response(_build_chat_prompt(request, bot_state))
    payload = _load_json(raw_text)
    if not payload:
        return None

    messages = payload.get("messages")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    if not isinstance(messages, list) or not messages:
        return None
    if len(messages) > 2:
        return None

    normalized_messages: list[str] = []
    for message in messages:
        if not isinstance(message, str):
            return None
        normalized = message.strip()
        if not normalized or len(normalized) > 160 or _has_forbidden_chat_content(normalized):
            return None
        normalized_messages.append(normalized)

    if any(_has_forbidden_chat_content(message) for message in normalized_messages):
        return None

    return {
        "messages": normalized_messages,
        "reason": reason.strip(),
    }


async def decide_vote_with_agent(request: VoteRequest) -> dict[str, Any] | None:
    if not _ai_mode_enabled() or not _llm_ready():
        return None

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    raw_text = await llm_adapter.generate_chat_response(_build_vote_prompt(request, bot_state))
    payload = _load_json(raw_text)
    if not payload:
        return None

    vote_target = payload.get("voteTarget")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    if not isinstance(vote_target, str):
        return None

    vote_target = vote_target.strip()
    if not vote_target:
        return None
    if vote_target == request.botId:
        return None
    if vote_target not in request.alivePlayers:
        return None
    if vote_target in request.infectedPlayers:
        return None

    return {
        "voteTarget": vote_target,
        "reason": reason.strip(),
    }