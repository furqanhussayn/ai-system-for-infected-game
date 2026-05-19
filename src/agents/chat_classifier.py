"""Classify latest meeting chat message for bot response strategy."""

from __future__ import annotations


def classify_latest_message(message: str, bot_id: str) -> str:
    msg = message.lower().strip()
    bot_lower = bot_id.lower()
    bot_num = bot_id.split("_")[-1].lower() if "_" in bot_id else bot_id.lower()
    targets_bot = bot_lower in msg or f"player {bot_num}" in msg or f"p{bot_num}" in msg

    vote_phrases = (
        "vote player 2",
        "vote him",
        "vote her",
        "kick player 2",
        "player 2 out",
        "its player 2",
        "it's player 2",
        "p2",
    )
    if any(p in msg for p in vote_phrases) and (targets_bot or bot_num == "2"):
        return "vote_bot"
    if "vote" in msg and targets_bot:
        return "vote_bot"
    if any(p in msg for p in ("kick", "eject")) and targets_bot:
        return "vote_bot"

    accusation_signals = (
        "sus",
        "infected",
        "weird",
        "acting",
        "following",
        "fake",
        "lying",
        "near gen",
        "near generator",
        "near body",
        "why is player",
        "chasing",
    )
    if (targets_bot or any(s in msg for s in ("following me", "near gen", "near generator", "near body"))) and any(s in msg for s in accusation_signals):
        return "direct_accusation"

    bot_real_signals = (
        "bot",
        " ai",
        "ai ",
        " real",
        "human",
        "npc",
        "are u even real",
        "you sound weird",
        "you sound wierd",
        "sound like a bot",
        "r u a bot",
        "ur a bot",
    )
    if any(s in msg for s in bot_real_signals):
        return "called_bot_or_real"

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

    insult_signals = (
        "stfu",
        "shut up",
        "dumb",
        "idiot",
        "no one asked",
        "nobody asked",
        "trash",
    )
    if any(s in msg for s in insult_signals):
        return "insult"

    return "generic"
