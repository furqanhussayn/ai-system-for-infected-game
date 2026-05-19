"""
Meeting Orchestrator — multi-bot responder selection for Chat Lab.

Decides WHO responds (and with what intent) before generating text.
Keeps single-bot /respond working for Unity by exposing simple helpers.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BotParticipant:
    player_id: str
    personality: str = "confused"
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
    "agree",
    "disagree",
    "confused",
    "pile_on",
    "calm_down_short",
    "stay_out",
    "third_party_opinion",
})

# ---------------------------------------------------------------------------
# Detective helpers
# ---------------------------------------------------------------------------

_PLAYER_2_PATTERNS = re.compile(
    r"\b(player\s*2|player_2|player2|p2)\b", re.IGNORECASE
)
_PLAYER_3_PATTERNS = re.compile(
    r"\b(player\s*3|player_3|player3|p3)\b", re.IGNORECASE
)
_PLAYER_4_PATTERNS = re.compile(
    r"\b(player\s*4|player_4|player4|p4)\b", re.IGNORECASE
)

_VOTE_PATTERN = re.compile(r"\b(vote|voted|kick|eject|out|contain)\b", re.IGNORECASE)


def detect_targeted_player(message: str) -> Optional[str]:
    """Detect which player (if any) the given message targets."""
    msg = message.lower().strip()

    # Check for "2 is" patterns (e.g. "2 is sus")
    if re.search(r"\b2 is\b", msg):
        return "player_2"

    # Check explicit player references
    if _PLAYER_2_PATTERNS.search(msg):
        return "player_2"
    if _PLAYER_3_PATTERNS.search(msg):
        return "player_3"
    if _PLAYER_4_PATTERNS.search(msg):
        return "player_4"

    # "vote him" / "vote her" — return None because context-dependent.
    # The caller with recent_chat should resolve this.
    return None


# ---------------------------------------------------------------------------
# Enhanced classification (multi-bot aware)
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
    msg = message.lower().strip()
    bot_lower = bot_id.lower()

    # Determine if this message targets THIS specific bot
    if targeted_player and targeted_player == bot_id:
        targets_this_bot = True
    else:
        targets_this_bot = bot_lower in msg

    # --- vote_bot ---
    if _VOTE_PATTERN.search(msg) and targets_this_bot:
        return "vote_bot"

    # --- direct_accusation ---
    accusation_signals = (
        "sus", "infected", "weird", "acting", "following",
        "fake", "lying", "ai", "bot", "real",
    )
    if targets_this_bot and any(s in msg for s in accusation_signals):
        return "direct_accusation"

    # --- called_bot_or_real ---
    bot_real_signals = (
        "bot", " ai", "ai ", " real", "human", "npc",
        "are u even real", "you sound weird", "you sound wierd",
        "sound like a bot", "r u a bot", "ur a bot",
    )
    if targets_this_bot and any(s in msg for s in bot_real_signals):
        return "called_bot_or_real"

    # Also check general mention (even if not targeting this bot)
    if any(s in msg for s in bot_real_signals):
        return "called_bot_or_real"

    # --- asks_who_infected ---
    if any(
        s in msg
        for s in (
            "who is infected",
            "who's infected",
            "whos infected",
            "who do u think",
            "who do you think",
            "who sus",
            "who is sus",
        )
    ):
        return "asks_who_infected"

    # --- insult ---
    insult_signals = (
        "stfu", "shut up", "dumb", "idiot",
        "no one asked", "nobody asked", "trash", "fuck up", "clown",
    )
    if any(s in msg for s in insult_signals):
        return "insult"

    return "generic"


# ---------------------------------------------------------------------------
# Responder selection
# ---------------------------------------------------------------------------

def _build_default_bots() -> list[BotParticipant]:
    return [
        BotParticipant(
            player_id="player_2",
            personality="deflector",
            talkativeness=0.6,
            aggression=0.4,
            confusion=0.2,
            defense_bias=0.8,
        ),
        BotParticipant(
            player_id="player_3",
            personality="accuser",
            talkativeness=0.55,
            aggression=0.7,
            confusion=0.1,
            defense_bias=0.2,
        ),
        BotParticipant(
            player_id="player_4",
            personality="confused",
            talkativeness=0.35,
            aggression=0.2,
            confusion=0.8,
            defense_bias=0.3,
        ),
    ]


def select_responders(
    latest_message: str,
    recent_chat: list | None = None,
    bots: list[BotParticipant] | None = None,
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
        bots = _build_default_bots()

    msg = latest_message.lower().strip()
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

    # --- Helper to get bot by id ---
    def _bot_by_id(pid: str) -> BotParticipant | None:
        for b in bots:
            if b.player_id == pid:
                return b
        return None

    # --- Helper to add plan ---
    def _add_plan(bot_id: str, intent: str, priority: int, reason: str, is_target: bool = False):
        plans.append(ResponderPlan(
            botId=bot_id, intent=intent, priority=priority,
            reason=reason, isDirectTarget=is_target,
        ))
        debug_info["selectedResponders"].append(bot_id)
        debug_info["selectionReasons"].append(f"{bot_id}: {reason}")

    # --- Direct target is player_2 ---
    if targeted_player == "player_2":
        p2 = _bot_by_id("player_2")
        if p2:
            # player_2 is direct target
            if force_response or random.random() < 0.95:
                _add_plan("player_2", "defend_self", 1, "direct target accused/deflector", True)
            elif force_response:
                _add_plan("player_2", "deflect", 1, "forced direct target", True)
                debug_info["forcedResponder"] = "player_2"

        # player_3 may pile on or comment
        p3 = _bot_by_id("player_3")
        if p3 and (force_response or random.random() < random.uniform(0.25, 0.45)):
            intent3 = random.choice(["pile_on", "accuse_other", "ask_question", "third_party_opinion"])
            _add_plan("player_3", intent3, 2, "instigator commenting on player_2")

        # player_4 quiet chance
        p4 = _bot_by_id("player_4")
        if p4 and (force_response or random.random() < random.uniform(0.15, 0.35)):
            _add_plan("player_4", "confused", 3, "confused reaction to accusation")

    # --- Direct target is player_3 ---
    elif targeted_player == "player_3":
        p3 = _bot_by_id("player_3")
        if p3:
            if force_response or random.random() < 0.95:
                _add_plan("player_3", "defend_self", 1, "direct target accused", True)
            elif force_response:
                _add_plan("player_3", "deflect", 1, "forced direct target", True)
                debug_info["forcedResponder"] = "player_3"

        # player_2 may pile on or redirect
        p2 = _bot_by_id("player_2")
        if p2 and (force_response or random.random() < random.uniform(0.25, 0.35)):
            _add_plan("player_2", "pile_on", 2, "deflector piling on player_3")

        # player_4 may ask question
        p4 = _bot_by_id("player_4")
        if p4 and (force_response or random.random() < random.uniform(0.15, 0.30)):
            _add_plan("player_4", "ask_question", 3, "confused asking about player_3")

    # --- Direct target is player_4 ---
    elif targeted_player == "player_4":
        p4 = _bot_by_id("player_4")
        if p4:
            if force_response or random.random() < 0.90:
                _add_plan("player_4", "defend_self", 1, "direct target accused", True)
            elif force_response:
                _add_plan("player_4", "confused", 1, "forced direct target", True)
                debug_info["forcedResponder"] = "player_4"

        # low chance others comment
        if random.random() < 0.20:
            _add_plan("player_2", "third_party_opinion", 2, "low-key comment on player_4")
        if random.random() < 0.20:
            _add_plan("player_3", "ask_question", 3, "accuser questioning about player_4")

    # --- General questions about infected ---
    elif classification == "asks_who_infected":
        count = random.choices([1, 2, 3], weights=[40, 40, 20])[0]
        if force_response and count < 1:
            count = 1

        responders_pool = ["player_2", "player_3", "player_4"]
        random.shuffle(responders_pool)

        selected = 0
        for pid in responders_pool:
            if selected >= count:
                break
            bot = _bot_by_id(pid)
            if not bot:
                continue
            if pid == "player_3" or random.random() < bot.talkativeness:
                if pid == "player_3":
                    intent = random.choice(["accuse_other", "third_party_opinion"])
                elif pid == "player_4":
                    intent = "confused"
                else:
                    intent = random.choice(["third_party_opinion", "accuse_other", "deflect"])
                _add_plan(pid, intent, selected + 1, f"responding to general infected question")
                selected += 1

    # --- Vote player X ---
    elif _VOTE_PATTERN.search(msg) and targeted_player:
        # target responds strongly
        target_bot = _bot_by_id(targeted_player)
        if target_bot:
            _add_plan(targeted_player, "deny", 1, "vote target panics", True)

        # one other may comment
        others = [b for b in bots if b.player_id != targeted_player]
        random.shuffle(others)
        if others and (force_response or random.random() < 0.6):
            other = others[0]
            intent = random.choice(["agree", "ask_question", "third_party_opinion", "pile_on"])
            _add_plan(other.player_id, intent, 2, "other bot commenting on vote")

        # high chaos chance for third
        if random.random() < 0.35 and len(others) > 1:
            _add_plan(others[1].player_id, "confused", 3, "chaos third comment")

    # --- Insult ---
    elif classification == "insult" and targeted_player:
        target_bot = _bot_by_id(targeted_player)
        if target_bot:
            _add_plan(targeted_player, "calm_down_short", 1, "insulted", True)

        if random.random() < 0.4:
            others = [b for b in bots if b.player_id != targeted_player]
            if others:
                other = random.choice(others)
                _add_plan(other.player_id, "calm_down_short", 2, "bystander calm down")

    # --- Generic ---
    elif classification == "generic":
        if force_response:
            # Force one random bot
            chosen = random.choice(bots)
            _add_plan(chosen.player_id, "third_party_opinion", 1, "forced generic response")
            debug_info["forcedResponder"] = chosen.player_id
        else:
            # 0-1 bot responds
            for bot in bots:
                if random.random() < bot.talkativeness * 0.5:
                    _add_plan(bot.player_id, "third_party_opinion", 1, "low chance generic")
                    break

    # --- Limit max responders ---
    max_responders = 3
    if len(plans) > max_responders:
        # Keep highest priority ones
        plans.sort(key=lambda p: p.priority)
        plans = plans[:max_responders]
        debug_info["selectionReasons"].append(f"capped at {max_responders} responders")

    # --- Silence handling ---
    if not plans:
        if force_response:
            # Last resort: force player_3 to say something
            _add_plan("player_3", "third_party_opinion", 99, "last-resort force")
            debug_info["forcedResponder"] = "player_3"
        else:
            debug_info["silenceReason"] = "No bot selected — silence triggered"

    return plans, debug_info


# ---------------------------------------------------------------------------
# Dynamic event delay calculation (multi-bot aware)
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
    length = len(text)
    base_delay = 1200 + length * 30

    # Direct target first reply: faster
    if is_direct_target and event_index == 0:
        base_delay = random.randint(600, 1600)
    # Urgent tiny reply
    elif len(text.split()) <= 2 and is_direct_target:
        base_delay = random.randint(500, 1200)
    # Third-party opinion: slower
    elif intent == "third_party_opinion" or intent == "confused":
        base_delay = random.randint(1800, 4200)
    # Normal reply
    else:
        base_delay = random.randint(1200, 2600)

    # Follow-up burst from same bot (event_index > 0)
    if event_index > 0:
        base_delay = random.randint(700, 1800)

    # Longer text gets longer delay
    if length > 55:
        base_delay += random.randint(300, 900)

    # Add jitter
    jitter = random.randint(-200, 400)
    total = base_delay + jitter

    # Clamp
    return max(500, min(total, 4500))


# ---------------------------------------------------------------------------
# Multi-bot fallback response generator
# ---------------------------------------------------------------------------

_P2_DEFEND_SELF = [
    "wtf i didnt even do anything",
    "i was literally at wires",
    "player 1 is pushing so hard rn",
    "nah this is rigged",
    "why me tho??",
    "ur literally just blaming me for no reason",
    "bro i was doing tasks the whole time",
    "u have no proof at all",
]

_P2_THIRD_PARTY = [
    "lowkey player 3 kinda sus",
    "idk player 1 pushing hard",
    "could be player 4 tbh",
    "nah something feels off",
    "why is player 1 so focused on me",
    "player 3 was moving weird ngl",
    "i think player 3 is acting weird",
]

_P3_ACCUSER = [
    "nah player 2 kinda weird tho",
    "player 1 yelling too much ngl",
    "someone is lying here fr",
    "wait where was player 2 then",
    "idk that sounds fake",
    "why is player 2 so defensive rn",
    "player 2 is acting mad sus",
    "i dont trust player 2 at all",
]

_P3_DEFEND = [
    "idk player 1 pushing kinda hard",
    "why vote so fast tho",
    "nah explain first",
    "why yall jumping on them so quick",
    "bro let them speak first",
]

_P4_CONFUSED = [
    "wait what happened",
    "idk i didnt see",
    "where was player 2?",
    "im lost ngl",
    "why are we voting already",
    "idk i wasnt paying attention",
    "what did i miss",
    "huh?",
    "...",
    "wait what",
]

_P4_ASK = [
    "so whats the proof tho",
    "can someone explain",
    "wait why player 2",
    "does anyone actually know",
]

_CALLED_BOT = [
    "bro what?? how do i sound like a bot",
    "ur saying that cuz i typed normal??",
    "what does that even mean lmao",
    "nah that's random af",
    "ok that makes no sense",
    "how is that even an argument",
]

_INSULT_RESPONSE = [
    "ok relax dude",
    "why u so mad??",
    "bro chill",
    "ur being weird rn",
    "no need to cry about it",
    "ok whatever",
]

_PILE_ON = [
    "fr tho",
    "yeah i noticed that too",
    "ok true",
    "nah he right actually",
    "i been saying that",
]

_DENY = [
    "nah thats cap",
    "thats not even true",
    "stop lying on me",
    "bro what",
]


def generate_human_fallback(
    message: str,
    bot_id: str,
    recent_chat: list | None = None,
    personality: str | None = None,
    intent: str = "third_party_opinion",
    targeted_player: str | None = None,
) -> list[str]:
    """
    Generate fallback chat messages based on personality, intent, and target.

    Returns a list of 1-5 messages.
    """
    if recent_chat is None:
        recent_chat = []

    msg_lower = message.lower().strip()

    # Determine if the message targets this bot
    this_bot_targeted = targeted_player == bot_id if targeted_player else False

    # Called bot / real — shared across personalities
    if "bot" in msg_lower or " ai" in msg_lower or "ai " in msg_lower or "real" in msg_lower:
        if "human" not in msg_lower and "npc" not in msg_lower:
            pass  # handled below
        count = random.choices([1, 2, 3], weights=[40, 40, 20])[0]
        replies = random.sample(_CALLED_BOT, min(count, len(_CALLED_BOT)))
        return replies[:3]

    # Vote/accusation against this bot
    if intent in ("defend_self", "deny", "deflect") or this_bot_targeted:
        if bot_id == "player_2":
            count = random.choices([1, 2, 3], weights=[30, 40, 30])[0]
            pool = _P2_DEFEND_SELF
        elif bot_id == "player_3":
            count = random.choices([1, 2, 3], weights=[40, 40, 20])[0]
            pool = _P3_DEFEND
        elif bot_id == "player_4":
            count = random.choices([1, 2], weights=[60, 40])[0]
            pool = _P4_CONFUSED + _P4_ASK
        else:
            count = 1
            pool = _CALLED_BOT

        replies = random.sample(pool, min(count, len(pool)))
        return replies[:3]

    # Insult
    if intent == "calm_down_short":
        replies = random.sample(_INSULT_RESPONSE, min(2, len(_INSULT_RESPONSE)))
        return replies

    # Ask question
    if intent == "ask_question":
        pool = _P4_ASK if bot_id == "player_4" else _P3_DEFEND
        return [random.choice(pool)]

    # Confused
    if intent == "confused":
        return [random.choice(_P4_CONFUSED)]

    # Pile on
    if intent == "pile_on":
        return [random.choice(_PILE_ON)]

    # Accuse other
    if intent == "accuse_other":
        if bot_id == "player_3":
            return [random.choice(_P3_ACCUSER)]
        elif bot_id == "player_2":
            return [random.choice(_P2_THIRD_PARTY)]
        else:
            return [random.choice(_P3_ACCUSER)]

    # Third-party opinion
    if intent == "third_party_opinion":
        if bot_id == "player_2":
            return [random.choice(_P2_THIRD_PARTY)]
        elif bot_id == "player_3":
            return [random.choice(_P3_ACCUSER)]
        elif bot_id == "player_4":
            return [random.choice(_P4_CONFUSED)]
        else:
            return [random.choice(_P2_THIRD_PARTY)]

    # Generic / default
    if bot_id == "player_2":
        return [random.choice(_P2_THIRD_PARTY)]
    elif bot_id == "player_3":
        return [random.choice(_P3_ACCUSER)]
    elif bot_id == "player_4":
        return [random.choice(_P4_CONFUSED)]

    return ["idk tbh"]