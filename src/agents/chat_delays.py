"""Typing delay metadata for meeting chat messages."""

from __future__ import annotations

import random


def calculate_message_delays(messages: list[str], classification: str) -> list[int]:
    if not messages:
        return []

    urgent = classification in ("vote_bot", "direct_accusation", "called_bot_or_real")
    slow_first = classification in ("generic", "asks_who_infected")
    delays: list[int] = []

    for i, msg in enumerate(messages):
        length = len(msg)
        base = 500 + length * 35
        jitter = random.randint(300, 900)

        if i == 0:
            if urgent:
                base = max(base - 350, 300)
            if slow_first:
                base += 400
            total = base + jitter
            if length > 55:
                total += 600
            total = max(500, min(total, 4200))
        else:
            base = 400 + length * 25
            jitter = random.randint(200, 700)
            total = base + jitter
            if length > 55:
                total += 600
            total = max(700, min(total, 3600))

        delays.append(int(total))

    return delays
