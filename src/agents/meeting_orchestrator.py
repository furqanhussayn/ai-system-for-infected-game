"""
Meeting Orchestrator — multi-bot responder selection for the live game.

Decides WHO responds, WHY they respond, and what fallback style they use.
Keeps single-bot /respond working by exposing reusable helpers.

Main public API kept stable:
- BotParticipant
- ResponderPlan
- detect_targeted_player(...)
- classify_latest_message(...)
- build_bot_participants_from_request(...)
- select_responders(...)
- calculate_event_delay(...)
- generate_human_fallback(...)
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Optional

from src.core.state import get_bot_state


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BotParticipant:
    player_id: str
    personality: str = "crowd_follower"
    talkativeness: float = 0.5
    aggression: float = 0.3
    confusion: float = 0.3
    defense_bias: float = 0.5


@dataclass
class ResponderPlan:
    botId: str
    intent: str
    priority: int = 0
    reason: str = ""
    isDirectTarget: bool = False


# ---------------------------------------------------------------------------
# Intent categories
# ---------------------------------------------------------------------------

ALLOWED_INTENTS = frozenset({
    "defend_self",
    "deny",
    "deflect",
    "accuse_other",
    "ask_question",
    "answer_question",
    "agree",
    "disagree",
    "confused",
    "pile_on",
    "calm_down_short",
    "stay_out",
    "third_party_opinion",
})

ALLOWED_PERSONALITIES = frozenset({
    "quiet",
    "deflector",
    "framer",
    "panicker",
    "crowd_follower",
})

PERSONALITY_PROFILES: dict[str, tuple[float, float, float, float]] = {
    "quiet": (0.25, 0.15, 0.68, 0.40),
    "deflector": (0.55, 0.35, 0.22, 0.82),
    "framer": (0.72, 0.76, 0.18, 0.26),
    "panicker": (0.50, 0.32, 0.80, 0.58),
    "crowd_follower": (0.46, 0.28, 0.40, 0.52),
}


# ---------------------------------------------------------------------------
# Regex / word banks
# ---------------------------------------------------------------------------

_PLAYER_PATTERNS: dict[str, re.Pattern[str]] = {
    "player_1": re.compile(r"\b(player\s*1|player_1|player1|p1)\b", re.IGNORECASE),
    "player_2": re.compile(r"\b(player\s*2|player_2|player2|p2)\b", re.IGNORECASE),
    "player_3": re.compile(r"\b(player\s*3|player_3|player3|p3)\b", re.IGNORECASE),
    "player_4": re.compile(r"\b(player\s*4|player_4|player4|p4)\b", re.IGNORECASE),
}

_SHORT_NUMBER_TARGET = re.compile(
    r"\b(?P<num>[1-4])\b\s*(is|was|sus|weird|infected|lying|fake|bot|ai|chasing|following|quiet|safe|clear)",
    re.IGNORECASE,
)

_VOTE_PATTERN = re.compile(
    r"\b(vote|voted|voting|kick|eject|out|contain|freeze|antidote)\b",
    re.IGNORECASE,
)

_ACCUSATION_WORDS = (
    "sus",
    "infected",
    "weird",
    "acting",
    "following",
    "chasing",
    "fake",
    "lying",
    "lied",
    "too quiet",
    "quiet",
    "not doing tasks",
    "didnt do task",
    "didn't do task",
    "standing there",
    "near gen",
    "near generator",
    "near body",
    "near exit",
    "ran away",
    "kept following",
    "stalking",
)

_BOT_REAL_WORDS = (
    "bot",
    " ai",
    "ai ",
    "npc",
    "real",
    "human",
    "scripted",
    "robot",
    "not real",
    "are u real",
    "are you real",
    "sound like a bot",
    "sounds like a bot",
    "r u a bot",
    "are u a bot",
    "are you a bot",
    "ur a bot",
    "you're a bot",
)

_ASK_WHO_WORDS = (
    "who is infected",
    "who's infected",
    "whos infected",
    "who do u think",
    "who do you think",
    "who sus",
    "who is sus",
    "who should we vote",
    "who we voting",
    "who do we vote",
    "any proof",
    "what proof",
)

_INSULT_WORDS = (
    "stfu",
    "shut up",
    "dumb",
    "idiot",
    "no one asked",
    "nobody asked",
    "trash",
    "fuck up",
    "clown",
    "ur stupid",
    "you're stupid",
)

_ROOM_WORDS = {
    "electrical": "electrical",
    "security": "security",
    "pipe": "pipe room",
    "pipes": "pipe room",
    "maintenance": "maintenance",
    "generator": "generator",
    "gen": "generator",
    "comms": "communications",
    "communication": "communications",
    "communications": "communications",
    "hub": "central hub",
    "central": "central hub",
    "exit": "exit gate",
    "gate": "exit gate",
    "scan": "exit gate",
    "wires": "wires",
    "wire": "wires",
}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _norm(text: str | None) -> str:
    return (text or "").lower().strip()


def _display_player(player_id: str | None) -> str:
    if not player_id:
        return "someone"
    if player_id.startswith("player_"):
        suffix = player_id.split("_", 1)[-1]
        if suffix.isdigit():
            return f"player {suffix}"
    return player_id.replace("_", " ")


def _safe_choice(pool: list[str], fallback: str = "idk tbh") -> str:
    if not pool:
        return fallback
    return random.choice(pool)


def _unique_sample(pool: list[str], count: int) -> list[str]:
    if not pool:
        return []
    count = max(1, min(count, len(pool)))
    return random.sample(pool, count)


def _chat_get(chat_item: Any, key: str, default: str = "") -> str:
    if isinstance(chat_item, dict):
        value = chat_item.get(key, default)
        return str(value) if value is not None else default
    value = getattr(chat_item, key, default)
    return str(value) if value is not None else default


def _recent_texts(recent_chat: list | None) -> list[str]:
    if not recent_chat:
        return []
    return [_chat_get(item, "text") for item in recent_chat if _chat_get(item, "text")]


def _contains_any(text: str, words: tuple[str, ...] | list[str]) -> bool:
    msg = _norm(text)
    return any(word in msg for word in words)


def _has_accusation(text: str) -> bool:
    return _contains_any(text, _ACCUSATION_WORDS)


def _has_bot_real_claim(text: str) -> bool:
    return _contains_any(text, _BOT_REAL_WORDS)


def _extract_room_hint(message: str, recent_chat: list | None = None) -> Optional[str]:
    all_text = [message] + _recent_texts(recent_chat)
    for text in all_text:
        msg = _norm(text)
        for key, room in _ROOM_WORDS.items():
            if re.search(rf"\b{re.escape(key)}\b", msg):
                return room
    return None


def _player_sort_key(player_id: str) -> int:
    match = re.search(r"(\d+)", player_id)
    return int(match.group(1)) if match else 99


def _other_players(exclude: set[str] | None = None, candidates: list[str] | None = None) -> list[str]:
    exclude = exclude or set()
    universe = candidates or [f"player_{index}" for index in range(1, 5)]
    return [player_id for player_id in universe if player_id not in exclude]


def _normalize_personality(personality: str | None) -> str | None:
    if not isinstance(personality, str):
        return None
    value = personality.strip().lower().replace("-", "_")
    return value if value in ALLOWED_PERSONALITIES else None


def _personality_profile(personality: str | None) -> tuple[float, float, float, float]:
    normalized = _normalize_personality(personality) or "crowd_follower"
    return PERSONALITY_PROFILES[normalized]


def _request_value(req: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(req, name):
            value = getattr(req, name)
            if value is not None:
                return value
    return default


def _extract_bot_ids_from_request(req: Any) -> list[str]:
    explicit_sources = []
    for field_name in ("botIds", "botParticipants", "participants"):
        raw_value = _request_value(req, field_name, default=None)
        if isinstance(raw_value, list):
            explicit_sources.extend(raw_value)

    extracted: list[str] = []
    for item in explicit_sources:
        if isinstance(item, str) and item.strip():
            extracted.append(item.strip())
        elif isinstance(item, dict):
            candidate = item.get("botId") or item.get("playerId") or item.get("id")
            if isinstance(candidate, str) and candidate.strip():
                extracted.append(candidate.strip())

    if extracted:
        return list(dict.fromkeys(extracted))

    infected_players = _request_value(req, "infectedPlayers", default=None)
    if isinstance(infected_players, list) and infected_players:
        infected_ids = [player_id.strip() for player_id in infected_players if isinstance(player_id, str) and player_id.strip()]
        if infected_ids:
            return list(dict.fromkeys(infected_ids))

    bot_id = _request_value(req, "botId", default=None)
    if isinstance(bot_id, str) and bot_id.strip():
        return [bot_id.strip()]

    return []


def _resolve_personality_for_bot(req: Any, bot_id: str) -> str:
    match_id = _request_value(req, "matchId", default="")
    bot_state = get_bot_state(match_id, bot_id) or {}
    personality = _normalize_personality(bot_state.get("personality"))

    if personality:
        return personality

    req_personality = _normalize_personality(_request_value(req, "personality", default=None))
    if bot_id == _request_value(req, "botId", default=None) and req_personality:
        return req_personality

    return "crowd_follower"


def build_bot_participants_from_request(req: Any) -> list[BotParticipant]:
    """Build bot participants from live request/state instead of fixed sample IDs."""
    if req is None:
        return []

    bot_ids = _extract_bot_ids_from_request(req)
    if not bot_ids:
        return []

    alive_players = {
        player_id.strip()
        for player_id in (_request_value(req, "alivePlayers", default=[]) or [])
        if isinstance(player_id, str) and player_id.strip()
    }

    recent_chat = _request_value(req, "recentChat", default=[])
    _recent_chat_count = len(recent_chat) if isinstance(recent_chat, list) else 0

    candidates = list(dict.fromkeys(bot_ids))
    if alive_players:
        candidates = [player_id for player_id in candidates if player_id in alive_players or player_id in bot_ids]

    participants: list[BotParticipant] = []
    match_id = _request_value(req, "matchId", default="")

    for bot_id in candidates:
        personality = _resolve_personality_for_bot(req, bot_id)
        talkativeness, aggression, confusion, defense_bias = _personality_profile(personality)
        bot_state = get_bot_state(match_id, bot_id) or {}
        participants.append(
            BotParticipant(
                player_id=bot_id,
                personality=personality,
                talkativeness=float(bot_state.get("talkativeness", talkativeness)),
                aggression=float(bot_state.get("aggression", aggression)),
                confusion=float(bot_state.get("confusion", confusion)),
                defense_bias=float(bot_state.get("defense_bias", defense_bias)),
            )
        )

    return participants


def build_demo_bot_participants() -> list[BotParticipant]:
    """Demo-only sample roster for local demo harnesses."""
    return [
        BotParticipant("player_2", "deflector", 0.62, 0.42, 0.15, 0.82),
        BotParticipant("player_3", "framer", 0.58, 0.72, 0.12, 0.28),
        BotParticipant("player_4", "quiet", 0.34, 0.22, 0.76, 0.35),
    ]


def _latest_accuser_against(
    target_player: str | None,
    recent_chat: list | None,
    latest_message: str = "",
) -> Optional[str]:
    """
    Find a recent sender who accused the target player.
    Best effort only. Returns player id or None.
    """
    if not target_player:
        return None

    chat_items = list(recent_chat or [])
    if latest_message:
        chat_items.append({"sender": "", "text": latest_message})

    for item in reversed(chat_items):
        text = _chat_get(item, "text")
        sender = _chat_get(item, "sender")
        if sender == target_player:
            continue
        if detect_targeted_player(text) == target_player and _has_accusation(text):
            return sender if sender else None

    return None


def _choose_counter_target(
    bot_id: str,
    targeted_player: str | None = None,
    recent_chat: list | None = None,
    message: str = "",
) -> str:
    """
    Pick a player to redirect suspicion toward.
    Prefer the latest accuser, otherwise choose a plausible non-bot target.
    """
    accuser = _latest_accuser_against(targeted_player or bot_id, recent_chat, message)
    if accuser and accuser != bot_id:
        return accuser

    candidates = _other_players(exclude={bot_id})
    if targeted_player:
        candidates = [p for p in candidates if p != targeted_player] or candidates

    # Bias toward player_1 because in Unity the real human commonly starts there,
    # but still allow variety so bot chat does not feel scripted.
    weighted = []
    for p in candidates:
        weight = 4 if p == "player_1" else 2
        weighted.extend([p] * weight)

    return random.choice(weighted) if weighted else "player_1"


# ---------------------------------------------------------------------------
# Detective helpers
# ---------------------------------------------------------------------------

def detect_targeted_player(message: str) -> Optional[str]:
    """Detect which player, if any, the given message targets."""
    msg = _norm(message)

    if not msg:
        return None

    # Explicit references first.
    for player_id, pattern in _PLAYER_PATTERNS.items():
        if pattern.search(msg):
            return player_id

    # Short natural phrases: "2 is sus", "3 was chasing", "vote 4"
    short = _SHORT_NUMBER_TARGET.search(msg)
    if short:
        return f"player_{short.group('num')}"

    # Vote number: "vote 2", "freeze 3"
    vote_num = re.search(r"\b(vote|freeze|antidote|contain)\s*(?P<num>[1-4])\b", msg)
    if vote_num:
        return f"player_{vote_num.group('num')}"

    # "2 sus", "3 weird", etc.
    num_accuse = re.search(
        r"\b(?P<num>[1-4])\s*(sus|weird|infected|fake|lying|bot|ai)\b",
        msg,
    )
    if num_accuse:
        return f"player_{num_accuse.group('num')}"

    return None


# ---------------------------------------------------------------------------
# Enhanced classification
# ---------------------------------------------------------------------------

def classify_latest_message(
    message: str,
    bot_id: str,
    targeted_player: Optional[str] = None,
) -> str:
    """
    Return one of:
      vote_bot, vote_other, direct_accusation, called_bot_or_real,
      asks_who_infected, insult, generic
    """
    msg = _norm(message)
    bot_id = bot_id or ""

    if targeted_player is None:
        targeted_player = detect_targeted_player(message)

    targets_this_bot = bool(bot_id and targeted_player == bot_id)

    if _has_bot_real_claim(msg):
        if not bot_id or targets_this_bot:
            return "called_bot_or_real"

    if _VOTE_PATTERN.search(msg):
        if targets_this_bot:
            return "vote_bot"
        if targeted_player:
            return "vote_other"

    if targeted_player and _has_accusation(msg):
        if targets_this_bot:
            return "direct_accusation"
        return "direct_accusation"

    if "?" in msg or _contains_any(
        msg,
        (
            "what happened",
            "what's happening",
            "whats happening",
            "what is happening",
            "what plan",
            "what's the plan",
            "whats the plan",
            "task progress",
            "how many tasks",
            "what wave",
            "which wave",
            "who saw",
            "where exactly",
            "what was the route",
            "what room",
            "did anyone see",
            "anyone see",
            "can someone explain",
            "who was near",
            "what did u see",
            "what did you see",
            "what were you doing",
            "where were you",
        ),
    ):
        return "question_prompt"

    if _contains_any(msg, _ASK_WHO_WORDS):
        return "asks_who_infected"

    if _contains_any(msg, _INSULT_WORDS):
        return "insult"

    return "generic"


def select_responders(
    latest_message: str,
    recent_chat: list | None = None,
    bots: list[BotParticipant] | None = None,
    request: Any | None = None,
    force_response: bool = False,
    debug: bool = False,
) -> tuple[list[ResponderPlan], dict]:
    """
    Decides WHICH bots respond and with what intent.

    Returns (list[ResponderPlan], debug_dict).
    """
    if recent_chat is None:
        recent_chat = []
    if bots is None:
        bots = build_bot_participants_from_request(request)
    if not bots:
        return [], {
            "classification": classify_latest_message(latest_message, "", detect_targeted_player(latest_message)),
            "targetedPlayer": detect_targeted_player(latest_message),
            "selectedResponders": [],
            "forcedResponder": None,
            "silenceReason": "No bot participants available",
            "selectionReasons": [],
        }

    msg = _norm(latest_message)
    targeted_player = detect_targeted_player(latest_message)
    classification = classify_latest_message(latest_message, "", targeted_player)

    plans: list[ResponderPlan] = []
    debug_info: dict = {
        "classification": classification,
        "targetedPlayer": targeted_player,
        "selectedResponders": [],
        "forcedResponder": None,
        "silenceReason": None,
        "selectionReasons": [],
    }

    bot_ids = {b.player_id for b in bots}

    def _bot_by_id(pid: str | None) -> BotParticipant | None:
        if not pid:
            return None
        for b in bots:
            if b.player_id == pid:
                return b
        return None

    def _add_plan(bot_id: str, intent: str, priority: int, reason: str, is_target: bool = False):
        if bot_id not in bot_ids:
            return
        if intent not in ALLOWED_INTENTS:
            intent = "third_party_opinion"
        # Avoid duplicate plans for same bot; upgrade priority if needed.
        for existing in plans:
            if existing.botId == bot_id:
                if priority < existing.priority:
                    existing.intent = intent
                    existing.priority = priority
                    existing.reason = reason
                    existing.isDirectTarget = is_target
                return
        plans.append(
            ResponderPlan(
                botId=bot_id,
                intent=intent,
                priority=priority,
                reason=reason,
                isDirectTarget=is_target,
            )
        )

    def _maybe_add_bystander(
        exclude: set[str],
        intents: list[str],
        chance: float,
        reason: str,
        priority: int,
    ):
        candidates = [b for b in bots if b.player_id not in exclude]
        random.shuffle(candidates)
        for bot in candidates:
            bot_chance = chance * max(0.25, bot.talkativeness)
            if force_response or random.random() < bot_chance:
                _add_plan(bot.player_id, random.choice(intents), priority, reason, False)
                return

    def _intent_from_personality(personality: str | None, *, direct_target: bool, classification_name: str) -> str:
        normalized = _normalize_personality(personality) or "crowd_follower"
        if direct_target:
            if normalized == "quiet":
                return random.choice(["defend_self", "ask_question", "deny"])
            if normalized == "deflector":
                return random.choice(["deny", "defend_self", "deflect"])
            if normalized == "framer":
                return random.choice(["accuse_other", "deflect", "pile_on"])
            if normalized == "panicker":
                return random.choice(["defend_self", "calm_down_short", "deny"])
            return random.choice(["defend_self", "disagree", "ask_question"])

        if classification_name in ("vote_bot", "direct_accusation"):
            if normalized == "framer":
                return random.choice(["accuse_other", "pile_on", "third_party_opinion"])
            if normalized == "deflector":
                return random.choice(["deflect", "disagree", "third_party_opinion"])
            if normalized == "quiet":
                return random.choice(["ask_question", "confused", "stay_out"])
            if normalized == "panicker":
                return random.choice(["defend_self", "calm_down_short", "ask_question"])
            return random.choice(["third_party_opinion", "agree", "ask_question"])

        if classification_name == "question_prompt":
            return random.choice(["answer_question", "third_party_opinion", "agree"])

        if normalized == "quiet":
            return random.choice(["stay_out", "ask_question", "confused"])
        if normalized == "deflector":
            return random.choice(["deflect", "deny", "third_party_opinion"])
        if normalized == "framer":
            return random.choice(["accuse_other", "pile_on", "ask_question"])
        if normalized == "panicker":
            return random.choice(["calm_down_short", "confused", "ask_question"])
        return random.choice(["third_party_opinion", "agree", "disagree"])

    # -----------------------------------------------------------------------
    # 1. Someone directly targeted a bot.
    # -----------------------------------------------------------------------
    if targeted_player in bot_ids:
        target_bot = _bot_by_id(targeted_player)
        target_class = classify_latest_message(latest_message, targeted_player, targeted_player)

        if target_bot:
            target_intent = _intent_from_personality(
                target_bot.personality,
                direct_target=True,
                classification_name=target_class,
            )

            direct_chance = 0.96 if _has_accusation(msg) or _VOTE_PATTERN.search(msg) else 0.82
            if force_response or random.random() < direct_chance:
                _add_plan(
                    targeted_player,
                    target_intent,
                    1,
                    f"direct target response; classification={target_class}",
                    True,
                )

        # Let one other bot add pressure or ask for proof.
        bystander_intents = ["ask_question", "third_party_opinion", "pile_on"]
        if classification in ("direct_accusation", "vote_bot"):
            bystander_intents = ["ask_question", "pile_on", "third_party_opinion"]
        if classification == "called_bot_or_real":
            bystander_intents = ["disagree", "ask_question", "third_party_opinion"]

        _maybe_add_bystander(
            exclude={targeted_player},
            intents=bystander_intents,
            chance=0.42,
            reason=f"bystander reacting to accusation on {_display_player(targeted_player)}",
            priority=2,
        )

        # Rare third voice when the chat is chaotic.
        if force_response or random.random() < 0.18:
            _maybe_add_bystander(
                exclude={targeted_player} | {p.botId for p in plans},
                intents=["confused", "calm_down_short", "ask_question"],
                chance=0.8,
                reason="third voice because meeting is getting chaotic",
                priority=3,
            )

    # -----------------------------------------------------------------------
    # 2. Someone directly targeted a human/non-bot, often player_1.
    # -----------------------------------------------------------------------
    elif targeted_player and targeted_player not in bot_ids:
        # Bots may pile on a human target, especially aggressive/framer bots.
        likely_commenters = sorted(
            bots,
            key=lambda b: (b.aggression + b.talkativeness),
            reverse=True,
        )

        if classification in ("direct_accusation", "vote_other"):
            first = likely_commenters[0] if likely_commenters else None
            if first and (force_response or random.random() < 0.75):
                _add_plan(
                    first.player_id,
                    random.choice(["pile_on", "accuse_other", "agree"]),
                    1,
                    f"human target {_display_player(targeted_player)} is being accused",
                    False,
                )

            _maybe_add_bystander(
                exclude={first.player_id if first else ""},
                intents=["ask_question", "third_party_opinion", "confused"],
                chance=0.35,
                reason="second bot comments on human accusation",
                priority=2,
            )
        else:
            _maybe_add_bystander(
                exclude=set(),
                intents=["ask_question", "third_party_opinion"],
                chance=0.28,
                reason="human was mentioned but not clearly accused",
                priority=2,
            )

    # -----------------------------------------------------------------------
    # 3. General question that should get an answer-first response.
    # -----------------------------------------------------------------------
    elif classification == "question_prompt":
        responder_count = random.choices([1, 2, 3], weights=[50, 35, 15])[0]
        if force_response:
            responder_count = max(1, responder_count)

        pool = bots[:]
        random.shuffle(pool)
        pool.sort(key=lambda b: (b.talkativeness, b.confusion), reverse=True)

        for idx, bot in enumerate(pool[:responder_count]):
            personality = _normalize_personality(bot.personality)
            if personality in ("crowd_follower", "panicker", "quiet") or random.random() < bot.talkativeness:
                intent = _intent_from_personality(personality, direct_target=False, classification_name=classification)
                if intent == "third_party_opinion" and random.random() < 0.65:
                    intent = "answer_question"
                _add_plan(bot.player_id, intent, idx + 1, "answering neutral meeting question")

    # -----------------------------------------------------------------------
    # 4. General "who is infected / who sus" question.
    # -----------------------------------------------------------------------
    elif classification == "asks_who_infected":
        responder_count = random.choices([1, 2, 3], weights=[45, 40, 15])[0]
        if force_response:
            responder_count = max(1, responder_count)

        pool = bots[:]
        random.shuffle(pool)

        # Framer/aggressive bots like answering these.
        pool.sort(key=lambda b: (b.aggression + b.talkativeness), reverse=True)

        for idx, bot in enumerate(pool[:responder_count]):
            personality = _normalize_personality(bot.personality)
            if personality == "framer" or random.random() < bot.talkativeness:
                intent = _intent_from_personality(personality, direct_target=False, classification_name=classification)
                _add_plan(bot.player_id, intent, idx + 1, "answering general suspicion question")

    # -----------------------------------------------------------------------
    # 5. Vote mentioned but target unclear.
    # -----------------------------------------------------------------------
    elif _VOTE_PATTERN.search(msg):
        if force_response or random.random() < 0.75:
            bot = random.choice(bots)
            _add_plan(
                bot.player_id,
                random.choice(["ask_question", "third_party_opinion", "confused"]),
                1,
                "vote mentioned without clear target",
            )

    # -----------------------------------------------------------------------
    # 6. Insult without clear target.
    # -----------------------------------------------------------------------
    elif classification == "insult":
        if force_response or random.random() < 0.55:
            bot = random.choice(bots)
            _add_plan(bot.player_id, "calm_down_short", 1, "meeting insult/noise")

    # -----------------------------------------------------------------------
    # 7. Generic message.
    # -----------------------------------------------------------------------
    else:
        if force_response:
            chosen = random.choice(bots)
            intent = _intent_from_personality(chosen.personality, direct_target=False, classification_name=classification)
            _add_plan(chosen.player_id, intent, 1, "forced generic response")
            debug_info["forcedResponder"] = chosen.player_id
        else:
            # Usually silence. Bot chat should not respond to everything.
            pool = bots[:]
            random.shuffle(pool)
            for bot in pool:
                chance = bot.talkativeness * 0.28
                if random.random() < chance:
                    intent = _intent_from_personality(bot.personality, direct_target=False, classification_name=classification)
                    _add_plan(bot.player_id, intent, 1, "low chance generic meeting comment")
                    break

    # -----------------------------------------------------------------------
    # Cap responders. Most real meetings should have 0-2 bots, 3 only sometimes.
    # -----------------------------------------------------------------------
    max_responders = 3
    if len(plans) > max_responders:
        plans.sort(key=lambda p: p.priority)
        plans = plans[:max_responders]
        debug_info["selectionReasons"].append(f"capped at {max_responders} responders")

    # -----------------------------------------------------------------------
    # Silence handling.
    # -----------------------------------------------------------------------
    if not plans:
        if force_response:
            fallback_bot = sorted(bots, key=lambda b: b.talkativeness, reverse=True)[0]
            _add_plan(
                fallback_bot.player_id,
                "third_party_opinion",
                99,
                "last-resort forced response",
            )
            debug_info["forcedResponder"] = fallback_bot.player_id
        else:
            debug_info["silenceReason"] = "No bot selected — natural silence"

    plans.sort(key=lambda p: p.priority)

    diversity_applied = False
    used_intents: set[str] = set()

    def _diverse_intent_options(personality: str | None, classification_name: str, position: int, direct_target: bool) -> list[str]:
        normalized = _normalize_personality(personality) or "crowd_follower"
        if direct_target:
            if normalized == "deflector":
                return ["deflect", "deny", "defend_self", "disagree", "third_party_opinion"]
            if normalized == "framer":
                return ["accuse_other", "pile_on", "ask_question", "third_party_opinion", "disagree"]
            if normalized == "quiet":
                return ["defend_self", "deny", "ask_question", "confused", "stay_out"]
            if normalized == "panicker":
                return ["defend_self", "calm_down_short", "deny", "ask_question", "confused"]
            return ["defend_self", "deny", "disagree", "ask_question", "third_party_opinion"]

        if position == 1:
            if classification_name in ("vote_bot", "direct_accusation", "called_bot_or_real"):
                return ["deflect", "ask_question", "third_party_opinion", "agree", "disagree"]
            if classification_name == "question_prompt":
                return ["answer_question", "third_party_opinion", "agree", "ask_question", "confused"]
            if normalized == "framer":
                return ["accuse_other", "pile_on", "third_party_opinion", "ask_question", "disagree"]
            if normalized == "deflector":
                return ["deflect", "deny", "third_party_opinion", "ask_question", "agree"]
            if normalized == "quiet":
                return ["confused", "calm_down_short", "stay_out", "ask_question", "third_party_opinion"]
            if normalized == "panicker":
                return ["calm_down_short", "confused", "ask_question", "defend_self", "deny"]
            return ["third_party_opinion", "agree", "disagree", "ask_question", "confused"]

        return ["confused", "calm_down_short", "stay_out", "third_party_opinion", "ask_question", "agree"]

    for index, plan in enumerate(plans):
        bot = _bot_by_id(plan.botId)
        if index == 0:
            used_intents.add(plan.intent)
            continue

        options = _diverse_intent_options(bot.personality if bot else None, classification, index, plan.isDirectTarget)
        if plan.intent in used_intents or (classification in ("vote_bot", "direct_accusation") and plan.intent == "ask_question"):
            for option in options:
                if option not in used_intents and option != plan.intent:
                    original_intent = plan.intent
                    plan.intent = option
                    plan.reason = f"{plan.reason} | diversified from {original_intent}"
                    diversity_applied = True
                    break
        used_intents.add(plan.intent)

    debug_info["selectedResponders"] = [p.botId for p in plans]
    debug_info["selectionReasons"].extend(
        [f"{p.botId}: {p.reason} -> {p.intent}" for p in plans]
    )
    debug_info["diversityApplied"] = diversity_applied

    return plans, debug_info


# ---------------------------------------------------------------------------
# Dynamic event delay calculation
# ---------------------------------------------------------------------------

def calculate_event_delay(
    sender: str,
    text: str,
    classification: str,
    intent: str,
    is_direct_target: bool,
    event_index: int,
) -> int:
    """
    Returns milliseconds delay for this event.
    No sleeping — just return ms.
    """
    text = text or ""
    length = len(text)
    word_count = len(text.split())

    # First direct replies feel fast.
    if is_direct_target and event_index == 0:
        base_delay = random.randint(650, 1650)

    # Tiny panic replies are fast.
    elif word_count <= 3 and intent in ("deny", "defend_self", "calm_down_short"):
        base_delay = random.randint(650, 1350)

    # Confused / third-party replies feel like the player is thinking.
    elif intent in ("third_party_opinion", "confused", "ask_question"):
        base_delay = random.randint(1700, 4100)

    # Pile-ons are quick.
    elif intent in ("pile_on", "agree"):
        base_delay = random.randint(850, 1900)

    # Normal reply.
    else:
        base_delay = random.randint(1200, 2800)

    # Follow-up from same bot: slightly quicker burst.
    if event_index > 0:
        base_delay = random.randint(750, 1850)

    # Longer text takes longer.
    if length > 45:
        base_delay += random.randint(250, 750)
    if length > 75:
        base_delay += random.randint(300, 900)

    # Classification modifiers.
    if classification in ("vote_bot", "direct_accusation"):
        base_delay -= random.randint(100, 350)
    elif classification == "asks_who_infected":
        base_delay += random.randint(100, 500)

    jitter = random.randint(-180, 420)
    total = base_delay + jitter

    return max(500, min(total, 4800))


# ---------------------------------------------------------------------------
# Fallback response pools
# ---------------------------------------------------------------------------

_SELF_DEFENSE = {
    "deflector": [
        "nah i was doing wires",
        "i was nowhere near them",
        "ur reaching so hard rn",
        "why are u ignoring what player 3 did",
        "i literally just came from {room}",
        "that makes no sense",
        "u keep saying my name with no proof",
        "i was with player 4 for a bit",
        "player 1 is pushing this way too fast",
        "i think ur trying to throw blame off urself",
        "bro i barely saw anyone",
        "check the timing again",
        "i passed hub then went task",
        "i didnt chase anyone",
        "that was not me",
        "u saw me for like two seconds",
        "how is walking behind someone proof",
        "i was going to my task",
        "this accusation is so random",
        "nah dont just vote off vibes",
    ],
    "framer": [
        "nah player 1 is the weird one",
        "why did player 1 wait so long to say that",
        "that sounds like a fake story",
        "i think player 1 is trying to control the vote",
        "player 3 was near {room} too btw",
        "why are we not talking about player 4",
        "u said that too late",
        "that story changed twice",
        "i dont trust that callout",
        "if anything player 1 looks worse here",
        "nah this is a setup",
        "u are blaming me because i called u out earlier",
        "where exactly did u see me",
        "say the exact room then",
        "who else saw that",
        "this sounds rehearsed ngl",
    ],
    "quiet": [
        "i didnt do that",
        "i was doing task",
        "not me",
        "i was in {room}",
        "i dont know what u saw",
        "i barely moved from task",
        "no i wasnt chasing",
        "i think u mixed me up",
        "i was away from there",
        "nah",
        "that wasnt me",
        "i was fixing wires",
    ],
    "panicker": [
        "wait what no",
        "bro no no that wasnt me",
        "why are u voting me already",
        "i was literally trying to do task",
        "hold on let me explain",
        "dont rush vote",
        "nah ur wrong",
        "i didnt even touch anyone",
        "why is everyone jumping on me",
        "i swear i was at {room}",
        "this is bad logic",
        "u guys are throwing",
    ],
    "crowd_follower": [
        "i dont think thats enough proof",
        "yeah idk about that",
        "i was doing task",
        "can someone confirm that",
        "lets not rush it",
        "i dont remember seeing u there",
        "that sounds off",
        "i was around {room}",
        "maybe check who was near hub",
        "i need actual proof first",
    ],
    "confused": [
        "wait why me",
        "i dont get it",
        "i was doing task i think",
        "when did that happen",
        "i was at {room}",
        "i didnt see u",
        "im confused",
        "what proof",
        "i dont think that was me",
        "huh no",
    ],
}

_DENIALS = [
    "nah thats cap",
    "thats not true",
    "stop lying on me",
    "bro what",
    "nope wasnt me",
    "thats just wrong",
    "u made that up",
    "i didnt do that",
    "not even close",
    "where is the proof",
    "say where then",
    "u saw wrong",
    "that was someone else",
]

_DEFLECT = [
    "why is nobody asking about {other}",
    "{other} was moving weird earlier",
    "i saw {other} near {room}",
    "{other} has been quiet the whole time",
    "this feels like {other} trying to dodge blame",
    "lowkey {other} is more sus than me",
    "what was {other} doing during gas",
    "i dont trust {other} rn",
    "{other} kept hovering near people",
    "can {other} explain their route",
    "everyone is ignoring {other} for some reason",
    "if u want a real lead check {other}",
    "{other} changed direction when meeting got called",
    "{other} was not doing tasks from what i saw",
]

_THIRD_PARTY = [
    "i saw movement near {room} but idk who",
    "the timing is kinda weird",
    "someone is definitely lying here",
    "i dont think we should insta vote",
    "we need actual route info",
    "who was in hub before meeting",
    "i only saw someone pass {room}",
    "task count is still low too",
    "this meeting is messy",
    "one of these stories doesnt match",
    "idk but player 1 is pushing hard",
    "who was alone during gas",
    "dont just vote because someone shouted first",
    "i think the quiet ones are more scary",
    "someone was camping near task panels",
    "i saw someone double back near {room}",
    "we need to remember who was with who",
    "the chase claim matters if anyone else saw it",
    "i dont have enough proof yet",
    "this sounds like a 50/50",
    "could be a bait accusation",
    "listen to the route first",
]

_ACCUSER = [
    "{other} was acting off",
    "{other} kept following people",
    "{other} went quiet after gas",
    "i dont like how {other} is playing",
    "{other} was near {room} earlier",
    "i think {other} is hiding behind the chaos",
    "{other} never said where they were",
    "why is {other} not explaining",
    "{other} was moving like they had no task",
    "i saw {other} stop near someone for too long",
    "{other} feels wrong this round",
    "{other} keeps saying nothing useful",
    "if we vote anyone it should be {other}",
    "{other} was the last one near hub",
    "i dont trust {other} at all",
]

_ASK_QUESTION = [
    "what proof do u have",
    "where exactly did that happen",
    "who saw it too",
    "what room was that in",
    "why did u wait to say it",
    "was anyone with them",
    "did they chase or just walk same way",
    "what was their route",
    "are we sure it wasnt a mixup",
    "who was near gas first",
    "how long were they following",
    "did they touch u or just pass by",
    "can someone confirm",
    "why vote so fast",
    "what task were u doing",
    "who was at {room}",
]

_CONFUSED = [
    "wait what happened",
    "idk i didnt see it",
    "im lost ngl",
    "why are we voting already",
    "what did i miss",
    "wait who are we saying",
    "huh",
    "i was doing wires",
    "i didnt see anyone",
    "can someone explain",
    "wait where was this",
    "i thought we were doing tasks",
    "idk this is confusing",
    "who called meeting",
    "are we voting or skipping",
    "i missed that completely",
    "wait is the claim about chasing",
    "i only saw people near hub",
    "im not sure tbh",
]

_CALM_DOWN = [
    "bro chill",
    "relax for a sec",
    "stop yelling and explain",
    "ok but whats the proof",
    "no need to be toxic",
    "just say what u saw",
    "arguing wont help",
    "calm down",
    "we still need evidence",
    "dont throw the round",
    "talk normal",
    "everyone chill",
]

_PILE_ON = [
    "yeah i noticed that too",
    "fr that was weird",
    "ok true",
    "that matches what i saw",
    "i was thinking the same thing",
    "yeah that route was strange",
    "nah he has a point",
    "that does sound sus",
    "i dont hate that vote",
    "kinda agree",
    "same, i saw something weird too",
    "yeah the timing is bad",
]

_AGREE = [
    "yeah",
    "true",
    "i agree",
    "that makes sense",
    "fair point",
    "yeah maybe",
    "could be",
    "i can see that",
    "not impossible",
]

_DISAGREE = [
    "nah that logic is weak",
    "i dont agree",
    "that doesnt prove anything",
    "could just be bad timing",
    "walking same way isnt proof",
    "i think thats a reach",
    "not enough for a vote",
    "i wouldnt vote on that",
    "that sounds random",
    "nah slow down",
]

_CALLED_BOT = [
    "bro what??",
    "how do i sound like a bot",
    "ur saying that cuz i typed normal?",
    "what does that even mean",
    "nah thats random",
    "ok that makes no sense",
    "how is that an argument",
    "im literally just typing",
    "u call everyone a bot when u have no proof",
    "that is not evidence",
    "focus on the game",
    "we are wasting meeting time",
    "saying bot is not a real accusation",
    "bro im trying to explain",
]

_GENERIC_IDLE = [
    "idk yet",
    "need more info",
    "this round is weird",
    "i dont trust this meeting",
    "someone is hiding something",
    "tasks still need doing",
    "we should track routes next round",
    "i barely saw anyone",
    "gas made everyone scatter",
    "keep an eye on hub",
    "dont split too hard",
    "i only saw people passing by",
]


def _format_pool(pool: list[str], *, room: str, other: str, target: str, bot: str) -> list[str]:
    return [
        line.format(
            room=room,
            other=_display_player(other),
            target=_display_player(target),
            bot=_display_player(bot),
        )
        for line in pool
    ]


def _personality_key(
    personality: str | None,
    *,
    classification: str = "",
    intent: str = "",
    targeted: bool = False,
) -> str:
    normalized = _normalize_personality(personality)
    if normalized in ALLOWED_PERSONALITIES:
        return normalized

    if targeted and classification in ("vote_bot", "direct_accusation", "called_bot_or_real"):
        return "deflector"
    if intent in ("accuse_other", "pile_on"):
        return "framer"
    if intent in ("calm_down_short", "defend_self", "deny"):
        return "panicker"
    if classification == "insult":
        return "panicker"

    return "crowd_follower"


def _message_count_for_intent(intent: str, direct: bool, personality: str) -> int:
    if intent in ("pile_on", "agree", "confused", "ask_question", "calm_down_short"):
        return 1

    if direct:
        if personality == "panicker":
            return random.choices([1, 2, 3], weights=[20, 50, 30])[0]
        if personality == "quiet":
            return random.choices([1, 2], weights=[75, 25])[0]
        return random.choices([1, 2, 3], weights=[35, 45, 20])[0]

    return random.choices([1, 2], weights=[70, 30])[0]


def _dedupe_keep_order(messages: list[str]) -> list[str]:
    seen = set()
    out = []
    for msg in messages:
        clean = " ".join((msg or "").strip().split())
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


# ---------------------------------------------------------------------------
# Multi-bot fallback response generator
# ---------------------------------------------------------------------------

def generate_human_fallback(
    message: str,
    bot_id: str,
    recent_chat: list | None = None,
    personality: str | None = None,
    intent: str = "third_party_opinion",
    targeted_player: str | None = None,
) -> list[str]:
    """
    Generate fallback chat messages based on personality, intent, target, and context.

    Returns a list of short messages. Usually 1-2, sometimes 3 for panic/defense.
    No LLM call here. No sleeping. No role reveal.
    """
    if recent_chat is None:
        recent_chat = []

    if targeted_player is None:
        targeted_player = detect_targeted_player(message)

    msg_lower = _norm(message)
    classification = classify_latest_message(message, bot_id, targeted_player)
    this_bot_targeted = targeted_player == bot_id
    personality_key = _personality_key(
        personality,
        classification=classification,
        intent=intent,
        targeted=this_bot_targeted,
    )
    room = _extract_room_hint(message, recent_chat) or random.choice(
        ["electrical", "security", "generator", "central hub", "communications", "wires"]
    )
    other = _choose_counter_target(bot_id, targeted_player, recent_chat, message)
    target = targeted_player or other
    this_bot_targeted = targeted_player == bot_id

    classification = classify_latest_message(message, bot_id, targeted_player)
    direct = this_bot_targeted or intent in ("defend_self", "deny", "deflect")

    formatted_self = _format_pool(
        _SELF_DEFENSE.get(personality_key, _SELF_DEFENSE["confused"]),
        room=room,
        other=other,
        target=target,
        bot=bot_id,
    )
    formatted_deflect = _format_pool(
        _DEFLECT,
        room=room,
        other=other,
        target=target,
        bot=bot_id,
    )
    formatted_third = _format_pool(
        _THIRD_PARTY,
        room=room,
        other=other,
        target=target,
        bot=bot_id,
    )
    formatted_accuser = _format_pool(
        _ACCUSER,
        room=room,
        other=other,
        target=target,
        bot=bot_id,
    )
    formatted_questions = _format_pool(
        _ASK_QUESTION,
        room=room,
        other=other,
        target=target,
        bot=bot_id,
    )

    # -----------------------------------------------------------------------
    # Called bot / real / AI accusation.
    # Keep this casual and never mention backend/provider/system.
    # -----------------------------------------------------------------------
    if classification == "called_bot_or_real":
        count = random.choices([1, 2], weights=[55, 45])[0]
        replies = _unique_sample(_CALLED_BOT, count)
        if count == 2 and random.random() < 0.45:
            replies.append(_safe_choice(formatted_questions))
        return _dedupe_keep_order(replies)[:3]

    # -----------------------------------------------------------------------
    # Direct defense.
    # -----------------------------------------------------------------------
    if intent in ("defend_self", "deny", "deflect") or this_bot_targeted:
        count = _message_count_for_intent(intent, True, personality_key)

        if intent == "deny":
            pool = _DENIALS + formatted_self
        elif intent == "deflect":
            pool = formatted_self + formatted_deflect
        else:
            pool = formatted_self + _DISAGREE + formatted_questions

        replies = _unique_sample(pool, count)

        # Make multi-message defense feel like real human logic:
        # denial -> route/proof -> redirect/question.
        if count >= 2:
            if random.random() < 0.55:
                replies[0] = _safe_choice(_DENIALS)
            if random.random() < 0.45:
                replies[-1] = _safe_choice(formatted_questions + formatted_deflect)

        return _dedupe_keep_order(replies)[:3]

    # -----------------------------------------------------------------------
    # Calm down after insult.
    # -----------------------------------------------------------------------
    if intent == "calm_down_short" or classification == "insult":
        count = random.choices([1, 2], weights=[75, 25])[0]
        return _dedupe_keep_order(_unique_sample(_CALM_DOWN, count))[:2]

    # -----------------------------------------------------------------------
    # Ask for proof.
    # -----------------------------------------------------------------------
    if intent == "ask_question":
        return [_safe_choice(formatted_questions)]

    # -----------------------------------------------------------------------
    # Answer a neutral meeting question with a short believable claim.
    # -----------------------------------------------------------------------
    if intent == "answer_question":
        answer_pool = _format_pool(
            [
                "i was at {room}",
                "task bar barely moved on my side",
                "i only saw people pass by",
                "i think the wave was just now",
                "i was doing tasks in {room}",
                "someone was near {room} before meeting",
                "i didnt see the full thing",
                "i was with {other} for a bit",
                "i was around {room} most of the round",
                "that happened right after i left {room}",
            ],
            room=room,
            other=other,
            target=target,
            bot=bot_id,
        )
        count = random.choices([1, 2], weights=[72, 28])[0]
        replies = _unique_sample(answer_pool, count)
        if count >= 2 and random.random() < 0.45:
            replies[-1] = _safe_choice(formatted_third + formatted_questions)
        return _dedupe_keep_order(replies)[:2]

    # -----------------------------------------------------------------------
    # Confused/quiet bot.
    # -----------------------------------------------------------------------
    if intent == "confused":
        count = random.choices([1, 2], weights=[80, 20])[0]
        return _dedupe_keep_order(_unique_sample(_CONFUSED, count))[:2]

    # -----------------------------------------------------------------------
    # Pile on / agree / disagree.
    # -----------------------------------------------------------------------
    if intent == "pile_on":
        if random.random() < 0.65:
            return [_safe_choice(_PILE_ON)]
        return [_safe_choice(formatted_accuser)]

    if intent == "agree":
        if random.random() < 0.45:
            return [_safe_choice(_AGREE)]
        return [_safe_choice(_PILE_ON)]

    if intent == "disagree":
        if random.random() < 0.55:
            return [_safe_choice(_DISAGREE)]
        return [_safe_choice(formatted_questions)]

    # -----------------------------------------------------------------------
    # Accuse another player.
    # -----------------------------------------------------------------------
    if intent == "accuse_other":
        count = random.choices([1, 2], weights=[70, 30])[0]
        pool = formatted_accuser + formatted_deflect
        replies = _unique_sample(pool, count)
        return _dedupe_keep_order(replies)[:2]

    # -----------------------------------------------------------------------
    # Third-party opinion.
    # -----------------------------------------------------------------------
    if intent == "third_party_opinion":
        if personality_key in ("framer", "deflector") and random.random() < 0.45:
            pool = formatted_third + formatted_accuser + formatted_deflect
        elif personality_key in ("quiet", "confused"):
            pool = formatted_third + _CONFUSED + formatted_questions
        else:
            pool = formatted_third + formatted_questions

        count = random.choices([1, 2], weights=[78, 22])[0]
        return _dedupe_keep_order(_unique_sample(pool, count))[:2]

    # -----------------------------------------------------------------------
    # Stay out / default.
    # -----------------------------------------------------------------------
    if intent == "stay_out":
        return [_safe_choice(["idk yet", "not enough proof", "i didnt see it"])]

    # Generic fallback.
    if _has_accusation(msg_lower):
        return [_safe_choice(formatted_questions + formatted_third)]

    return [_safe_choice(_GENERIC_IDLE)]