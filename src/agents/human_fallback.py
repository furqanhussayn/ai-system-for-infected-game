"""Rule-based human-style meeting chat fallback responses."""

from __future__ import annotations

import random

from src.agents.chat_classifier import classify_latest_message
from src.agents.chat_style_guard import clean_message, is_bad_bot_output

_RESPONSE_POOLS: dict[str, list[str]] = {
    "asks_who_infected": [
        "idk tbh player 3 was moving weird",
        "lowkey player 4 kinda sus",
        "could be anyone rn ngl",
        "idk stop asking like i know",
        "player 3 maybe idk",
    ],
    "called_bot_or_real": [
        "bro what?? how do i sound like a bot",
        "ur saying that cuz i typed normal??",
        "what does that even mean lmao",
        "nah that's such a random thing to say",
        "ok now ur just making stuff up",
    ],
    "vote_bot": [
        "WAIT why me??",
        "bro yall throwing so hard",
        "nah vote player 3 he started this",
        "player 1 pushing way too fast",
        "wtf i didnt even do anything",
    ],
    "direct_accusation": [
        "nah i was at wires",
        "why u pushing me so hard??",
        "player 1 accusing way too fast ngl",
        "bro i didnt even do anything",
        "ur just blaming me for no reason",
    ],
    "insult": [
        "ok relax dude",
        "why u so mad??",
        "bro chill",
        "ur being weird rn",
        "no need to cry about it",
    ],
    "generic": [
        "idk tbh",
        "nah that makes no sense",
        "wait what??",
        "lowkey i dont trust player 3",
        "...",
    ],
}

_FOLLOWUP_POOLS: dict[str, list[str]] = {
    "called_bot_or_real": [
        "like what did i even say",
        "ur actually being so weird rn",
        "bro chill",
    ],
    "vote_bot": [
        "i was literally at wires",
        "player 1 is pushing so hard rn",
        "wtf yall",
        "nah this is rigged",
    ],
    "direct_accusation": [
        "u have no proof",
        "literally why me",
        "player 1 has to be deflecting",
    ],
    "insult": [
        "ok whatever",
        "nah ok",
    ],
}

_ULTRA_SAFE = ("idk tbh", "bro what??")


def _pick_count(classification: str) -> int:
    if classification == "generic":
        return random.choices([0, 1], weights=[15, 85])[0]
    if classification == "asks_who_infected":
        return 1
    if classification == "insult":
        return random.choices([0, 1, 2], weights=[15, 70, 15])[0]
    if classification == "direct_accusation":
        return random.choices([1, 2, 3], weights=[35, 45, 20])[0]
    if classification == "called_bot_or_real":
        return random.choices([1, 2, 3], weights=[30, 50, 20])[0]
    if classification == "vote_bot":
        return random.choices([1, 2, 3, 4, 5], weights=[15, 30, 30, 15, 10])[0]
    return 1


def _pick_messages(classification: str, count: int) -> list[str]:
    if count <= 0:
        return []

    bank = _RESPONSE_POOLS.get(classification, _RESPONSE_POOLS["generic"])
    followups = _FOLLOWUP_POOLS.get(classification, [])

    first = random.choice(bank)
    msgs = [first]

    if count > 1 and followups:
        extras = random.sample(followups, min(count - 1, len(followups)))
        msgs.extend(extras)
    elif count > 1:
        rest = [t for t in bank if t != first]
        if rest:
            extras = random.sample(rest, min(count - 1, len(rest)))
            msgs.extend(extras)

    cleaned: list[str] = []
    for m in msgs[:5]:
        c = clean_message(m)
        if c and not is_bad_bot_output(c):
            cleaned.append(c)
    return cleaned[:5]


def generate_human_fallback(
    message: str,
    bot_id: str,
    recent_chat: list | None = None,
) -> list[str]:
    classification = classify_latest_message(message, bot_id)
    count = _pick_count(classification)
    messages = _pick_messages(classification, count)

    if not messages:
        backup = random.choice(_ULTRA_SAFE)
        return [clean_message(backup)]

    if any(is_bad_bot_output(m) for m in messages):
        backup = random.choice(_ULTRA_SAFE)
        return [clean_message(backup)]

    return messages
