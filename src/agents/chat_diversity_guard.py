"""Reusable event-level chat diversity guard for meeting chat."""

from __future__ import annotations

from typing import Any

from src.agents.chat_style_guard import (
    dedupe_and_replace_messages as _dedupe_and_replace_messages,
    is_duplicate_message as _is_duplicate_message,
    message_opening_key,
    normalize_message_key,
)


def _normalize_text_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [str(value) for value in values if str(value).strip()]


def _build_event_context(
    *,
    used_messages: list[str] | None = None,
    recent_chat: list[str] | None = None,
    latest_human_message: str = "",
    used_message_keys: list[str] | None = None,
    used_openers: list[str] | None = None,
    used_intents: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "usedMessages": _normalize_text_list(used_messages),
        "usedMessageKeys": _normalize_text_list(used_message_keys),
        "usedOpeners": _normalize_text_list(used_openers),
        "usedIntents": _normalize_text_list(used_intents),
        "latestHumanMessage": latest_human_message,
        "recentChatTexts": _normalize_text_list(recent_chat),
    }


def is_near_duplicate(
    text: str,
    used_messages: list[str] | None = None,
    recent_chat: list[str] | None = None,
) -> bool:
    seen_messages = _normalize_text_list(used_messages) + _normalize_text_list(recent_chat)
    seen_keys = {normalize_message_key(value) for value in seen_messages if value}
    seen_openers = {message_opening_key(value) for value in seen_messages if value}
    return _is_duplicate_message(
        text,
        seen_messages,
        seen_keys=seen_keys,
        seen_openers=seen_openers,
    )


def filter_or_replace_messages(
    messages: list[str],
    *,
    used_messages: list[str] | None = None,
    recent_chat: list[str] | None = None,
    latest_human_message: str = "",
    used_message_keys: list[str] | None = None,
    used_openers: list[str] | None = None,
    used_intents: list[str] | None = None,
    intent: str = "third_party_opinion",
) -> tuple[list[str], dict[str, Any]]:
    event_context = _build_event_context(
        used_messages=used_messages,
        recent_chat=recent_chat,
        latest_human_message=latest_human_message,
        used_message_keys=used_message_keys,
        used_openers=used_openers,
        used_intents=used_intents,
    )
    return _dedupe_and_replace_messages(messages, event_context=event_context, intent=intent)


def apply_event_diversity(
    event_context: dict[str, Any] | None,
    messages: list[str],
    *,
    intent: str = "third_party_opinion",
) -> tuple[list[str], dict[str, Any]]:
    context = dict(event_context or {})
    if intent == "answer_question":
        latest_human_message = str(context.get("latestHumanMessage", "") or "").strip()
        if latest_human_message:
            latest_key = normalize_message_key(latest_human_message)
            recent_chat_texts = [
                text
                for text in _normalize_text_list(context.get("recentChatTexts", []))
                if normalize_message_key(text) != latest_key
                and text.strip().lower() != latest_human_message.lower()
            ]
            context["recentChatTexts"] = recent_chat_texts
            context["latestHumanMessage"] = ""

    return _dedupe_and_replace_messages(messages, event_context=context, intent=intent)


__all__ = [
    "normalize_message_key",
    "is_near_duplicate",
    "filter_or_replace_messages",
    "apply_event_diversity",
]
