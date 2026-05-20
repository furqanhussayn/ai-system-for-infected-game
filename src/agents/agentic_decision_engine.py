from __future__ import annotations

import json
import re
from typing import Any

from src.agents.chat_style_guard import clean_message, is_bad_bot_output
from src.agents.meeting_chat_prompt import build_meeting_chat_prompt
from src.agents import prompt_budgeter
from src.core import config
from src.core.state import get_bot_state
from src.models.schemas import DecideRequest, RespondRequest, VoteRequest
from src.services import llm_adapter
from src.services import llm_router


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_BEHAVIOR_MODES = {
    "stealth_fake_task",
    "stalk",
    "aggressive_chase",
    "final_hunt",
    "frozen",
    "idle",
}

CHASE_MODES = {"aggressive_chase", "final_hunt"}

SAFE_NON_CHASE_MODES = {"stealth_fake_task", "stalk", "frozen", "idle"}

FORBIDDEN_CHAT_PHRASES = [
    "ai",
    "as an ai",
    "language model",
    "prompt",
    "system",
    "system prompt",
    "groq",
    "gemini",
    "openrouter",
    "antigravity",
    "backend",
    "api",
    "code",
    "instructions",
    "secret role",
    "hidden role",
    "i am infected",
    "i'm infected",
    "im infected",
    "we are infected",
    "infected list",
    "known infected",
]

BEHAVIOR_MODE_ALIASES = {
    "fake_task": "stealth_fake_task",
    "fake task": "stealth_fake_task",
    "fake-task": "stealth_fake_task",
    "stealth": "stealth_fake_task",
    "stealth_task": "stealth_fake_task",
    "stealth fake task": "stealth_fake_task",
    "stealth-fake-task": "stealth_fake_task",
    "pretend_task": "stealth_fake_task",
    "pretend task": "stealth_fake_task",
    "stalking": "stalk",
    "follow": "stalk",
    "following": "stalk",
    "shadow": "stalk",
    "chase": "aggressive_chase",
    "aggressive": "aggressive_chase",
    "aggressive chase": "aggressive_chase",
    "aggressive-chase": "aggressive_chase",
    "hunt": "final_hunt",
    "final hunt": "final_hunt",
    "final-hunt": "final_hunt",
    "final_hunting": "final_hunt",
    "freeze": "frozen",
    "pause": "frozen",
    "none": "idle",
    "wait": "idle",
}

VALID_PHASES = {
    "Lobby",
    "ExplorationA",
    "GasWave",
    "ExplorationB",
    "Meeting",
    "AntidoteVote",
    "AntidoteFreeze",
    "FinalChase",
    "Ended",
}

ROOM_HINTS = {
    "CentralHub",
    "Central Hub",
    "Electrical",
    "Electrical Room",
    "Security",
    "Security Room",
    "PipeRoom",
    "Pipe Room",
    "Maintenance",
    "Maintenance Area",
    "Generator",
    "Generator Room",
    "Communications",
    "Communications Room",
    "ExitGate",
    "Exit Gate",
    "Wires",
    "Unknown",
}

CHAT_MAX_MESSAGES = 3
CHAT_MAX_CHARS = 90


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _ai_mode_enabled() -> bool:
    return str(getattr(config, "AI_MODE", "rules")).strip().lower() == "agent"


def _llm_ready() -> bool:
    """
    The current project normally uses Groq through llm_adapter.
    Keep this permissive but safe so rules fallback still works if no key exists.
    """
    provider = str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower()

    groq_key = str(getattr(config, "GROQ_API_KEY", "") or "").strip()
    gemini_key = str(getattr(config, "GEMINI_API_KEY", "") or "").strip()

    if provider == "gemini":
        return bool(gemini_key or groq_key)

    return bool(groq_key)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _req_get(req: Any, field: str, default: Any = None) -> Any:
    value = getattr(req, field, default)
    return default if value is None else value


def _phase(req: Any) -> str:
    raw = _normalize_text(_req_get(req, "phase", "Unknown"))
    return raw if raw else "Unknown"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _player_label(player_id: str | None) -> str:
    if not player_id:
        return "unknown"
    if player_id.startswith("player_"):
        suffix = player_id.split("_", 1)[-1]
        if suffix.isdigit():
            return f"Player {suffix}"
    return player_id.replace("_", " ").title()


def _normalize_personality(value: Any) -> str:
    if not isinstance(value, str):
        return "crowd_follower"
    lowered = value.strip().lower().replace("-", "_")
    return lowered if lowered in {"quiet", "deflector", "framer", "panicker", "crowd_follower"} else "crowd_follower"


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(value)


async def _call_llm(prompt: str) -> str | None:
    """
    Calls the adapter safely. Any LLM/API failure returns None so local fallback
    systems can continue the game.
    """
    try:
        raw = await llm_adapter.generate_chat_response(prompt)
    except Exception:
        return None

    if isinstance(raw, llm_adapter.LLMResult):
        return raw.text.strip() or None
    if not isinstance(raw, str):
        return None

    raw = raw.strip()
    return raw if raw else None


async def _call_llm_result(prompt: str) -> llm_adapter.LLMResult:
    return await llm_router.generate_for_chat(
        prompt,
        model=None,
        purpose="respond",
        max_output_tokens=int(getattr(config, "LLM_MAX_OUTPUT_TOKENS", 80)),
        temperature=0.7,
    )


# ---------------------------------------------------------------------------
# JSON loading / repair
# ---------------------------------------------------------------------------

def _strip_code_fence(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    return text.strip()


def _extract_first_json_object(text: str) -> str | None:
    """
    Extract the first balanced {...} object from messy LLM output.
    """
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start: idx + 1]

    return None


def _load_json(text: str | None) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None

    cleaned = _strip_code_fence(text)

    # First try direct JSON.
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Then try extracting object from extra text.
    obj = _extract_first_json_object(cleaned)
    if not obj:
        return None

    try:
        parsed = json.loads(obj)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Safety / validation helpers
# ---------------------------------------------------------------------------

def _has_forbidden_chat_content(text: str) -> bool:
    lowered = text.lower()

    for phrase in FORBIDDEN_CHAT_PHRASES:
        phrase = phrase.lower().strip()
        if not phrase:
            continue

        if " " in phrase:
            if phrase in lowered:
                return True
        else:
            if re.search(rf"\b{re.escape(phrase)}\b", lowered):
                return True

    return False


def _normalize_behavior_mode(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None

    lowered = raw.lower().replace("-", "_").strip()

    if lowered in ALLOWED_BEHAVIOR_MODES:
        return lowered

    alias_key = raw.lower().strip()
    alias_key = alias_key.replace("_", " ").replace("-", " ")
    alias_key = re.sub(r"\s+", " ", alias_key)

    if alias_key in BEHAVIOR_MODE_ALIASES:
        return BEHAVIOR_MODE_ALIASES[alias_key]

    alias_key_underscore = alias_key.replace(" ", "_")
    if alias_key_underscore in BEHAVIOR_MODE_ALIASES:
        return BEHAVIOR_MODE_ALIASES[alias_key_underscore]

    return None


def _valid_human_targets(req: DecideRequest) -> list[str]:
    humans = [p for p in _as_list(req.humanPlayers) if isinstance(p, str) and p.strip()]
    alive = {p for p in _as_list(req.alivePlayers) if isinstance(p, str) and p.strip()}

    if alive:
        humans = [p for p in humans if p in alive]

    return [p for p in humans if p != req.botId]


def _valid_vote_targets(req: VoteRequest) -> list[str]:
    alive = [p for p in _as_list(req.alivePlayers) if isinstance(p, str) and p.strip()]
    infected = {p for p in _as_list(req.infectedPlayers) if isinstance(p, str) and p.strip()}

    targets = [
        p for p in alive
        if p != req.botId and p not in infected
    ]

    humans = [p for p in _as_list(req.humanPlayers) if isinstance(p, str) and p.strip()]
    if humans:
        human_set = set(humans)
        human_targets = [p for p in targets if p in human_set]
        if human_targets:
            return human_targets

    return targets


def _valid_target_player(req: DecideRequest, target_player: Any) -> str | None:
    if target_player is None:
        return None

    if not isinstance(target_player, str):
        return None

    target_player = target_player.strip()
    if not target_player:
        return None

    if target_player not in _valid_human_targets(req):
        return None

    return target_player


def _valid_vote_target(req: VoteRequest, vote_target: Any) -> str | None:
    if vote_target is None:
        return None

    if not isinstance(vote_target, str):
        return None

    vote_target = vote_target.strip()
    if not vote_target:
        return None

    return vote_target if vote_target in _valid_vote_targets(req) else None


def _normalize_target_room(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return None

    room = value.strip()
    if not room:
        return None

    # Allow unknown dynamic room names from Unity, but clean obvious garbage.
    if len(room) > 60:
        return None

    if re.search(r"[{}[\]<>]", room):
        return None

    return room


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def _should_chase_for_mode(mode: str) -> bool:
    return mode in CHASE_MODES


def _is_final_context(req: DecideRequest) -> bool:
    phase = _phase(req)
    is_final_flag = bool(_req_get(req, "isFinalChase", False))
    human_count = len(_valid_human_targets(req))
    return is_final_flag or phase == "FinalChase" or human_count == 1


def _choose_default_target(req: DecideRequest) -> str | None:
    nearest = _valid_target_player(req, _req_get(req, "nearestHuman", None))
    if nearest:
        return nearest

    humans = _valid_human_targets(req)
    return humans[0] if humans else None


def _decision_pressure(req: DecideRequest) -> str:
    human_count = len(_valid_human_targets(req))
    infected_count = len([
        p for p in _as_list(req.infectedPlayers)
        if isinstance(p, str) and p.strip()
    ])
    task_progress = _safe_int(_req_get(req, "taskProgress", 0), 0)
    wave = _safe_int(_req_get(req, "wave", 0), 0)

    if _is_final_context(req):
        return "final_chase"
    if infected_count >= human_count and human_count > 1:
        return "infection_advantage"
    if task_progress >= 7:
        return "tasks_nearly_done"
    if wave <= 1:
        return "early_stealth"
    if wave >= 3:
        return "late_pressure"
    return "mid_game"


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_decide_prompt(req: DecideRequest, bot_state: dict[str, Any]) -> str:
    human_targets = _valid_human_targets(req)
    default_target = _choose_default_target(req)
    phase = _phase(req)
    pressure = _decision_pressure(req)
    bot_personality = _normalize_personality(bot_state.get("personality"))

    return (
        "Return strict JSON only. No markdown. No code fences. No explanation outside JSON.\n"
        "You are the infected bot behavior director for THE INFECTED, a 4-player top-down mobile horror social deduction game.\n\n"
        "Your job:\n"
        "- Choose high-level intent only.\n"
        "- Unity handles pathfinding, collision, infection triggers, and movement.\n"
        "- Do not output movement coordinates.\n"
        "- Do not invent player IDs.\n"
        "- Do not choose infected players as targets.\n\n"
        "Allowed behaviorMode values:\n"
        "- stealth_fake_task: fake normal task behavior and avoid obvious aggression.\n"
        "- stalk: drift toward a human or room without full chase.\n"
        "- aggressive_chase: pressure humans when infection has advantage or tasks are high.\n"
        "- final_hunt: only when FinalChase or exactly one human remains.\n"
        "- frozen: only if bot should not move.\n"
        "- idle: only if no useful action exists.\n\n"
        "Decision strategy:\n"
        "- Early game: mostly stealth_fake_task, sometimes stalk.\n"
        "- Mid game: stalk nearest human or suspicious room.\n"
        "- If infected count >= human count: aggressive_chase is allowed.\n"
        "- If taskProgress is 7 or higher: increase pressure.\n"
        "- If FinalChase or one human remains: final_hunt.\n"
        "- shouldChase must be true only for aggressive_chase or final_hunt.\n"
        "- shouldChase must be false for stealth_fake_task, stalk, frozen, idle.\n\n"
        "Strict JSON schema:\n"
        "{"
        "\"behaviorMode\":\"stealth_fake_task|stalk|aggressive_chase|final_hunt|frozen|idle\","
        "\"targetPlayer\":\"player_x or null\","
        "\"targetRoom\":\"room name or null\","
        "\"shouldChase\":true,"
        "\"reason\":\"short reason\""
        "}\n\n"
        f"matchId: {req.matchId}\n"
        f"botId: {req.botId}\n"
        f"botPersonality: {bot_personality}\n"
        f"phase: {phase}\n"
        f"wave: {_req_get(req, 'wave', 0)}\n"
        f"cycle: {_req_get(req, 'cycle', 0)}\n"
        f"taskProgress: {_req_get(req, 'taskProgress', 0)}/8\n"
        f"pressureState: {pressure}\n"
        f"alivePlayers: {_compact_json(_as_list(req.alivePlayers))}\n"
        f"infectedPlayers: {_compact_json(_as_list(req.infectedPlayers))}\n"
        f"humanPlayers: {_compact_json(_as_list(req.humanPlayers))}\n"
        f"validTargetPlayers: {_compact_json(human_targets)}\n"
        f"defaultTargetIfNeeded: {default_target}\n"
        f"nearestHuman: {_req_get(req, 'nearestHuman', None)}\n"
        f"botRoom: {_req_get(req, 'botRoom', None) or bot_state.get('botRoom') or 'unknown'}\n"
        f"nearestHumanRoom: {_req_get(req, 'nearestHumanRoom', None) or 'unknown'}\n"
        f"secondsSinceLastSeenHuman: {_req_get(req, 'secondsSinceLastSeenHuman', 999)}\n"
    )


def _build_chat_prompt(req: RespondRequest, bot_state: dict[str, Any]) -> str:
    base = build_meeting_chat_prompt(req, bot_state=bot_state)

    return (
        "Return strict JSON only. No markdown. No code fences. No explanation outside JSON.\n"
        "You are generating chat for ONE infected bot pretending to be a normal player.\n"
        "You must obey the embedded meeting prompt below.\n\n"
        "Strict JSON schema:\n"
        "{"
        "\"messages\":[\"msg1\",\"msg2\"],"
        "\"reason\":\"short reason\""
        "}\n\n"
        "Example output (must be valid JSON):\n"
        "{\"messages\":[\"i was at electrical\",\"i did tasks\"],\"reason\":\"saw someone near gen\"}\n\n"
        "IMPORTANT: Return compact single-line JSON only (no newlines, no pretty formatting).\n"
        "Message rules:\n"
        "- messages may be [] for silence.\n"
        "- 1 message is most common.\n"
        "- 2 messages when accused or pressured.\n"
        "- 3 messages max.\n"
        "- each message max 90 characters.\n"
        "- no markdown.\n"
        "- no quotes inside messages unless natural.\n"
        "- no AI/model/system/backend/API words.\n"
        "- never reveal infected role.\n"
        "- do not use | inside message strings.\n\n"
        f"Stored bot state: {_compact_json(bot_state)}\n\n"
        "Embedded meeting prompt:\n"
        f"{base}"
    )


def _build_vote_prompt(req: VoteRequest, bot_state: dict[str, Any]) -> str:
    valid_targets = _valid_vote_targets(req)

    return (
        "Return strict JSON only. No markdown. No explanation.\n"
        "You are deciding an infected bot's antidote vote in THE INFECTED.\n\n"
        "Voting meaning:\n"
        "- This is antidote voting, not elimination.\n"
        "- The chosen target will be frozen and may be cured if recently infected.\n"
        "- As infected, prefer voting for a human target.\n"
        "- Never vote for yourself.\n"
        "- Never vote known infected if a human target exists.\n"
        "- If multiple infected bots exist, they must never vote for each other while humans remain valid.\n"
        "- If someone accused you, counter-vote that accuser if valid.\n"
        "- If no accuser is obvious, vote a valid human who is pushing hardest or most dangerous.\n\n"
        "Strict JSON schema:\n"
        "{"
        "\"voteTarget\":\"player_x or null\","
        "\"reason\":\"short reason\""
        "}\n\n"
        f"botId: {req.botId}\n"
        f"phase: {_req_get(req, 'phase', 'AntidoteVote')}\n"
        f"wave: {_req_get(req, 'wave', 0)}\n"
        f"cycle: {_req_get(req, 'cycle', 0)}\n"
        f"alivePlayers: {_compact_json(_as_list(req.alivePlayers))}\n"
        f"humanPlayers: {_compact_json(_as_list(_req_get(req, 'humanPlayers', [])))}\n"
        f"infectedPlayers: {_compact_json(_as_list(req.infectedPlayers))}\n"
        f"validVoteTargets: {_compact_json(valid_targets)}\n"
        f"recentChat: {_compact_json(_as_list(req.recentChat))}\n"
        f"botRoom: {bot_state.get('botRoom') or 'unknown'}\n"
    )


# ---------------------------------------------------------------------------
# Decision validation / repair
# ---------------------------------------------------------------------------

def _validate_decide_payload(
    request: DecideRequest,
    payload: dict[str, Any],
    *,
    allow_repair: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    behavior_mode = _normalize_behavior_mode(payload.get("behaviorMode"))
    if not behavior_mode:
        return None, f"invalid behaviorMode: {payload.get('behaviorMode')!r}"

    is_final = _is_final_context(request)
    human_targets = _valid_human_targets(request)

    if behavior_mode == "final_hunt" and not is_final:
        if allow_repair:
            behavior_mode = "aggressive_chase" if human_targets else "idle"
        else:
            return None, "final_hunt only allowed during FinalChase or one-human state"

    if behavior_mode in {"aggressive_chase", "stalk", "final_hunt"} and not human_targets:
        if allow_repair:
            behavior_mode = "idle"
        else:
            return None, "chase/stalk mode requires valid human target"

    raw_target = payload.get("targetPlayer")
    target_player = _valid_target_player(request, raw_target)

    if raw_target is not None and target_player is None and not allow_repair:
        return None, f"invalid targetPlayer: {raw_target!r}"

    if behavior_mode in {"aggressive_chase", "stalk", "final_hunt"} and target_player is None:
        target_player = _choose_default_target(request)

    if behavior_mode in {"stealth_fake_task", "frozen", "idle"}:
        # These modes do not need a player target.
        target_player = target_player if behavior_mode == "stealth_fake_task" else None

    target_room = _normalize_target_room(payload.get("targetRoom"))

    if target_room is None:
        nearest_room = _normalize_target_room(_req_get(request, "nearestHumanRoom", None))
        bot_room = _normalize_target_room(_req_get(request, "botRoom", None))
        if behavior_mode in {"stalk", "aggressive_chase", "final_hunt"}:
            target_room = nearest_room or bot_room
        elif behavior_mode == "stealth_fake_task":
            target_room = bot_room or "CentralHub"

    should_chase = _coerce_bool(payload.get("shouldChase"), default=_should_chase_for_mode(behavior_mode))
    expected_chase = _should_chase_for_mode(behavior_mode)

    if should_chase != expected_chase:
        if allow_repair:
            should_chase = expected_chase
        else:
            return None, f"shouldChase mismatch for {behavior_mode}"

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        if allow_repair:
            reason = f"{behavior_mode} selected from current match pressure."
        else:
            return None, "reason must be a non-empty string"

    reason = reason.strip()
    if len(reason) > 180:
        reason = reason[:177].rstrip() + "..."

    return {
        "behaviorMode": behavior_mode,
        "targetPlayer": target_player,
        "targetRoom": target_room,
        "shouldChase": should_chase,
        "reason": reason,
    }, None


# ---------------------------------------------------------------------------
# Public behavior functions
# ---------------------------------------------------------------------------

async def decide_behavior_with_agent(request: DecideRequest) -> dict[str, Any] | None:
    """
    Ask the LLM agent for a high-level bot behavior decision.

    Returns None if agent mode is off, LLM is unavailable, output is invalid,
    or safety validation fails. Local endpoint fallback should handle None.
    """
    if not _ai_mode_enabled():
        return None

    if not _llm_ready():
        provider = str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower() or "groq"
        model = config.GROQ_MODEL if provider == "groq" else config.GEMINI_MODEL
        missing_result = llm_adapter.LLMResult(
            ok=False,
            provider=provider,
            model=model,
            stage="missing_api_key",
            errorType="MissingAPIKey",
            errorMessage="LLM key is not configured.",
            llmUsed=False,
        )
        return {
            "messages": [],
            "reason": "missing_api_key",
            "llmDebug": _llm_debug_from_result(
                missing_result,
                llm_attempted=True,
                llm_used=False,
                fallback_reason="missing_api_key",
            ),
        }

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    llm_result = await _call_llm_result(_build_decide_prompt(request, bot_state))
    if not llm_result.ok:
        return {
            "behaviorMode": "idle",
            "targetPlayer": None,
            "targetRoom": request.botRoom if hasattr(request, "botRoom") else None,
            "shouldChase": False,
            "reason": llm_result.stage or "llm_failed",
            "llmDebug": _llm_debug_from_result(
                llm_result,
                llm_attempted=True,
                llm_used=False,
                fallback_reason=llm_result.stage or llm_result.errorType or "llm_failed",
            ),
        }

    payload = _load_json(llm_result.text)
    if not payload:
        return None

    result, _error = _validate_decide_payload(request, payload, allow_repair=True)
    if result is None:
        return None

    result["llmDebug"] = _llm_debug_from_result(
        llm_result,
        llm_attempted=True,
        llm_used=True,
        fallback_reason="",
        stage="json_repaired" if payload else llm_result.stage,
    )
    return result


async def validate_decide_behavior_with_agent(
    request: DecideRequest,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Same as decide_behavior_with_agent, but returns a specific validation error.
    Useful for tests and trace/debug tooling.
    """
    if not _ai_mode_enabled():
        return None, None

    if not _llm_ready():
        return None, "missing_api_key"

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    llm_result = await _call_llm_result(_build_decide_prompt(request, bot_state))

    if not llm_result.ok:
        return None, llm_result.stage or llm_result.errorType or "llm_call_failed"

    payload = _load_json(llm_result.text)
    if not payload:
        return None, "invalid_json"

    return _validate_decide_payload(request, payload, allow_repair=False)


# ---------------------------------------------------------------------------
# Chat generation
# ---------------------------------------------------------------------------

def _normalize_messages(value: Any) -> list[str] | None:
    if value is None:
        return []

    if isinstance(value, str):
        # Some models ignore JSON array and return one string.
        value = value.strip()
        if not value:
            return []
        parts = [p.strip() for p in value.split("|")]
        return [p for p in parts if p]

    if not isinstance(value, list):
        return None

    messages: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if stripped:
            messages.append(stripped)

    return messages


def _clean_and_validate_messages(messages: list[str]) -> list[str] | None:
    if len(messages) > CHAT_MAX_MESSAGES:
        return None

    cleaned_messages: list[str] = []
    seen: set[str] = set()

    for raw in messages:
        if not isinstance(raw, str):
            return None

        # Do not allow pipe inside a message because API expects separate messages.
        raw = raw.replace("|", " ").strip()

        normalized = clean_message(raw)
        if not normalized:
            continue

        # Keep messages short and mobile-chat-like.
        if len(normalized) > CHAT_MAX_CHARS:
            normalized = normalized[:CHAT_MAX_CHARS].rstrip()

        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            continue

        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)

        if _has_forbidden_chat_content(normalized):
            return None

        if is_bad_bot_output(normalized):
            return None

        cleaned_messages.append(normalized)

    if len(cleaned_messages) > CHAT_MAX_MESSAGES:
        return None

    return cleaned_messages


def _repair_plain_text_chat_messages(raw_text: str | None) -> list[str] | None:
    if not isinstance(raw_text, str):
        return None

    text = _strip_code_fence(raw_text).strip()
    if not text:
        return []

    parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(parts) <= 1:
        parts = [part.strip() for part in re.split(r"[\r\n]+", text) if part.strip()]
    if len(parts) <= 1:
        parts = [text]

    cleaned_messages: list[str] = []
    for raw in parts[:CHAT_MAX_MESSAGES]:
        candidate = clean_message(raw.replace("|", " "))
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if not candidate:
            continue
        if len(candidate) > CHAT_MAX_CHARS:
            candidate = candidate[:CHAT_MAX_CHARS].rstrip()
        if _has_forbidden_chat_content(candidate) or is_bad_bot_output(candidate):
            return None
        cleaned_messages.append(candidate)

    return cleaned_messages if cleaned_messages else None


def _llm_debug_from_result(
    result: llm_adapter.LLMResult,
    *,
    llm_attempted: bool,
    llm_used: bool,
    fallback_reason: str = "",
    stage: str | None = None,
) -> dict[str, Any]:
    failure_chain = result.failureChain or []
    return {
        "llmAttempted": llm_attempted,
        "llmUsed": llm_used,
        "fallbackReason": fallback_reason,
        "provider": result.provider,
        "providerUsed": result.provider,
        "model": result.model,
        "modelUsed": result.model,
        "keyIdUsed": result.keyId,
        "stage": stage or result.stage,
        "statusCode": result.statusCode,
        "latencyMs": result.latencyMs,
        "rawPreview": result.rawPreview,
        "errorType": result.errorType,
        "errorMessage": result.errorMessage,
        "attemptCount": result.attemptCount,
        "failureChain": failure_chain,
    }


async def generate_chat_with_agent(
    request: RespondRequest,
    *,
    intent: str | None = None,
    targeted_player: str | None = None,
    is_targeted: bool = False,
    event_context: dict | None = None,
) -> dict[str, Any] | None:
    """Generate meeting chat using the LLM agent with structured diagnostics."""
    if not _ai_mode_enabled() or not _llm_ready():
        return None

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    # Classify situation locally and build a compact prompt via the budgeter
    situation = prompt_budgeter.classify_chat_situation(request, bot_state=bot_state)

    # If local rules decide silence, avoid calling LLM to save tokens.
    if situation.responseNeed == "stay_silent":
        return {
            "messages": [],
            "reason": "local_silence",
            "llmDebug": {
                "llmAttempted": False,
                "llmUsed": False,
                "fallbackReason": "local_silence",
                "provider": config.LLM_PROVIDER,
                "model": config.GROQ_MODEL,
                "stage": "local_silence",
                "statusCode": None,
                "latencyMs": 0,
                "rawPreview": "",
                "errorType": "",
                "errorMessage": "",
                "attemptCount": 0,
                "promptChars": 0,
                "recentChatSent": situation.recentRelevantChat,
                "promptMode": situation.promptMode,
                "classification": situation.classification,
                "intent": situation.intent,
                "targetedPlayer": situation.targetedPlayer,
            },
        }

    prompt = prompt_budgeter.build_compact_chat_prompt(request, situation, bot_state=bot_state)
    prompt_chars = prompt_budgeter.estimate_prompt_chars(prompt)

    # Allow chat model selection override so small-model chat can be used by default.
    original_groq_model = getattr(config, "GROQ_MODEL", None)
    try:
        if not getattr(config, "LLM_USE_70B_FOR_CHAT", False):
            config.GROQ_MODEL = getattr(config, "GROQ_CHAT_MODEL", config.GROQ_MODEL)
        # Prefer a test-time monkeypatched generator on the respond module if present.
        # In production, route Groq calls through the key failover router.
        llm_result = None
        try:
            from src.api.endpoints import respond as _respond_module

            public_fn = getattr(_respond_module, "generate_chat_response", None)
            if public_fn and callable(public_fn) and public_fn is not llm_adapter.generate_chat_response:
                maybe = await public_fn(prompt)
                llm_result = llm_adapter._coerce_public_call_result(maybe)
        except Exception:
            llm_result = None

        if llm_result is None:
            llm_result = await _call_llm_result(prompt)
    finally:
        if original_groq_model is not None:
            config.GROQ_MODEL = original_groq_model

    if not llm_result.ok:
        fallback_reason = llm_result.stage or llm_result.errorType or "llm_failed"
        if llm_result.provider == "groq" and llm_result.failureChain:
            fallback_reason = "all_groq_keys_failed"
        return {
            "messages": [],
            "reason": fallback_reason,
            "llmDebug": _llm_debug_from_result(
                llm_result,
                llm_attempted=True,
                llm_used=False,
                fallback_reason=fallback_reason,
            ),
        }

    payload = _load_json(llm_result.text)
    if payload:
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "llm_chat_response"
        if _has_forbidden_chat_content(reason):
            reason = "safe chat decision"
        reason = reason.strip()
        if len(reason) > 180:
            reason = reason[:177].rstrip() + "..."

        messages_raw = payload.get("messages")
        if messages_raw is None and isinstance(payload.get("message"), str):
            messages_raw = payload.get("message")

        messages_values = _normalize_messages(messages_raw)
        if messages_values is not None:
            messages = _clean_and_validate_messages(messages_values)
            if messages is not None:
                debug = _llm_debug_from_result(
                    llm_result,
                    llm_attempted=True,
                    llm_used=bool(messages),
                    fallback_reason="",
                    stage="json_repaired" if messages_values != messages else llm_result.stage,
                )
                # Add prompt budgeting stats
                debug.update({
                    "promptChars": prompt_chars,
                    "recentChatSent": situation.recentRelevantChat,
                    "promptMode": situation.promptMode,
                    "classification": situation.classification,
                    "intent": situation.intent,
                    "targetedPlayer": situation.targetedPlayer,
                })
                return {
                    "messages": messages,
                    "reason": reason,
                    "llmDebug": debug,
                }
            return {
                "messages": [],
                "reason": "unsafe_message",
                "llmDebug": _llm_debug_from_result(
                    llm_result,
                    llm_attempted=True,
                    llm_used=False,
                    fallback_reason="unsafe_message",
                    stage="unsafe_message",
                ),
            }

    repaired_messages = _repair_plain_text_chat_messages(llm_result.text)
    if repaired_messages is not None:
        debug = _llm_debug_from_result(
            llm_result,
            llm_attempted=True,
            llm_used=True,
            fallback_reason="",
            stage="plain_text_repaired",
        )
        debug.update({
            "promptChars": prompt_chars,
            "recentChatSent": situation.recentRelevantChat,
            "promptMode": situation.promptMode,
            "classification": situation.classification,
            "intent": situation.intent,
            "targetedPlayer": situation.targetedPlayer,
        })
        return {
            "messages": repaired_messages,
            "reason": "plain_text_llm_output",
            "llmDebug": debug,
        }

    debug = _llm_debug_from_result(
        llm_result,
        llm_attempted=True,
        llm_used=False,
        fallback_reason="invalid_json",
        stage=llm_result.stage or "invalid_json",
    )
    debug.update({
        "promptChars": prompt_chars,
        "recentChatSent": situation.recentRelevantChat,
        "promptMode": situation.promptMode,
        "classification": situation.classification,
        "intent": situation.intent,
        "targetedPlayer": situation.targetedPlayer,
    })
    return {
        "messages": [],
        "reason": "invalid_json",
        "llmDebug": debug,
    }


# ---------------------------------------------------------------------------
# Vote validation / strategy
# ---------------------------------------------------------------------------

def _extract_accusers_against_bot(request: VoteRequest) -> list[str]:
    """
    Best-effort recent chat scanner.
    Finds humans/alive players who accused this bot.
    """
    bot_id = request.botId
    bot_number = bot_id.split("_")[-1] if "_" in bot_id else ""
    bot_patterns = [
        bot_id.lower(),
        bot_id.replace("_", " ").lower(),
        f"p{bot_number}",
        bot_number,
    ]

    accusation_words = [
        "sus",
        "infected",
        "weird",
        "following",
        "chasing",
        "fake",
        "lying",
        "bot",
        "ai",
        "vote",
        "freeze",
        "antidote",
    ]

    valid_targets = set(_valid_vote_targets(request))
    accusers: list[str] = []

    for item in _as_list(request.recentChat):
        sender = ""
        text = ""

        if isinstance(item, dict):
            sender = _normalize_text(item.get("sender") or item.get("senderId"))
            text = _normalize_text(item.get("text"))
        else:
            sender = _normalize_text(getattr(item, "sender", "") or getattr(item, "senderId", ""))
            text = _normalize_text(getattr(item, "text", ""))

        if not sender or sender not in valid_targets:
            continue

        lowered = text.lower()
        mentions_bot = any(re.search(rf"\b{re.escape(p)}\b", lowered) for p in bot_patterns if p)
        accuses = any(word in lowered for word in accusation_words)

        if mentions_bot and accuses and sender not in accusers:
            accusers.append(sender)

    return accusers


def _validate_vote_payload(
    request: VoteRequest,
    payload: dict[str, Any],
    *,
    allow_repair: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    valid_targets = _valid_vote_targets(request)

    if not valid_targets:
        return {
            "voteTarget": None,
            "reason": "No valid human vote target available.",
        }, None

    raw_target = payload.get("voteTarget")
    vote_target = _valid_vote_target(request, raw_target)

    if vote_target is None:
        if allow_repair:
            accusers = _extract_accusers_against_bot(request)
            vote_target = accusers[0] if accusers else valid_targets[0]
        else:
            return None, f"invalid voteTarget: {raw_target!r}"

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        if allow_repair:
            reason = "Selected a valid human target."
        else:
            return None, "reason must be a non-empty string"

    reason = reason.strip()
    if _has_forbidden_chat_content(reason):
        reason = "Strategic vote target."

    if len(reason) > 180:
        reason = reason[:177].rstrip() + "..."

    return {
        "voteTarget": vote_target,
        "reason": reason,
    }, None


async def decide_vote_with_agent(request: VoteRequest) -> dict[str, Any] | None:
    """
    Ask the LLM agent for a bot antidote vote.

    Returns None if agent is unavailable or unsafe, so endpoint fallback can choose.
    """
    if not _ai_mode_enabled():
        return None

    if not _llm_ready():
        return {
            "voteTarget": None,
            "reason": "missing_api_key",
            "llmDebug": _llm_debug_from_result(
                llm_adapter.LLMResult(
                    ok=False,
                    provider=str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower() or "groq",
                    model=config.GROQ_MODEL if str(getattr(config, "LLM_PROVIDER", "groq")).strip().lower() == "groq" else config.GEMINI_MODEL,
                    stage="missing_api_key",
                    errorType="MissingAPIKey",
                    errorMessage="LLM key is not configured.",
                    llmUsed=False,
                ),
                llm_attempted=True,
                llm_used=False,
                fallback_reason="missing_api_key",
            ),
        }

    bot_state = get_bot_state(request.matchId, request.botId) or {}
    llm_result = await _call_llm_result(_build_vote_prompt(request, bot_state))
    if not llm_result.ok:
        return {
            "voteTarget": None,
            "reason": llm_result.stage or "llm_failed",
            "llmDebug": _llm_debug_from_result(
                llm_result,
                llm_attempted=True,
                llm_used=False,
                fallback_reason=llm_result.stage or llm_result.errorType or "llm_failed",
            ),
        }

    payload = _load_json(llm_result.text)
    if not payload:
        return None

    result, _error = _validate_vote_payload(request, payload, allow_repair=False)
    if result is None:
        return None

    result["llmDebug"] = _llm_debug_from_result(
        llm_result,
        llm_attempted=True,
        llm_used=True,
        fallback_reason="",
    )
    return result