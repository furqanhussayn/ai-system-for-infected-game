from __future__ import annotations

import random

from fastapi import APIRouter

from src.agents.agentic_decision_engine import generate_chat_with_agent
from src.agents.chat_classifier import classify_latest_message
from src.agents.chat_delays import calculate_message_delays
from src.agents.chat_style_guard import clean_message, is_bad_bot_output, sanitize_messages
from src.agents.human_fallback import generate_human_fallback as original_human_fallback

# Keep local alias for compatibility with existing code in this file
generate_human_fallback = original_human_fallback
from src.agents.meeting_chat_prompt import build_meeting_chat_prompt
from src.agents.trace_logger import add_trace
from src.core import config
from src.models.schemas import RespondRequest, RespondResponse
from src.services.llm_adapter import generate_chat_response

router = APIRouter()

_RESPONSE_CHANCE: dict[str, float] = {
    "vote_bot": 1.00,
    "direct_accusation": 1.00,
    "called_bot_or_real": 1.00,
    "insult": 0.75,
    "asks_who_infected": 0.65,
    "generic": 0.25,
}

_ULTRA_SAFE = ("idk tbh", "bro what??")


def _message_text(item) -> str:
    if hasattr(item, "text"):
        return str(getattr(item, "text", ""))
    return str(item.get("text", ""))


def _message_sender(item) -> str:
    if hasattr(item, "sender"):
        return str(getattr(item, "sender", ""))
    return str(item.get("sender", ""))


def _accuses_bot(message: str, req: RespondRequest) -> bool:
    msg = message.lower()
    bot_num = req.botId.split("_")[-1].lower() if "_" in req.botId else req.botId.lower()
    bot_name = req.botName.lower().strip()
    markers = [
        req.botId.lower(),
        f"player {bot_num}",
        f"p{bot_num}",
        bot_name,
        "sus",
        "following",
        "chasing",
        "weird",
        "quiet",
        "near gen",
        "near generator",
        "near body",
        "why is player",
        "he was following me",
    ]
    return any(marker and marker in msg for marker in markers)


def _should_respond(classification: str, personality: str | None = None) -> bool:
    if personality == "quiet" and classification not in ("vote_bot", "direct_accusation", "called_bot_or_real"):
        return random.random() <= 0.55
    if personality == "quiet":
        return random.random() <= 0.75
    if personality == "panicker":
        return random.random() <= 0.95
    chance = _RESPONSE_CHANCE.get(classification, 0.25)
    return random.random() <= chance


def _format_trace(
    classification: str,
    messages: list[str],
    *,
    llm_used: bool,
    fallback_used: bool,
    delays_ms: list[int],
    extra: str = "",
) -> str:
    parts = [
        f"classification={classification}",
        f"message_count={len(messages)}",
        f"llm_used={llm_used}",
        f"fallback_used={fallback_used}",
        f"delaysMs={delays_ms}",
    ]
    if extra:
        parts.append(extra)
    return " | ".join(parts)


def _ultra_safe_messages() -> list[str]:
    return [clean_message(random.choice(_ULTRA_SAFE))]


def _ensure_safe(messages: list[str]) -> list[str]:
    safe = [clean_message(m) for m in messages if clean_message(m)]
    safe = [m for m in safe if m and not is_bad_bot_output(m)]
    if safe:
        return safe[:2]
    return _ultra_safe_messages()


def _delay_seconds(classification: str, personality: str | None, message_count: int) -> tuple[float, float]:
    if message_count <= 0:
        return 0.0, 0.0

    if personality == "quiet":
        typing_delay = random.uniform(3.0, 5.5)
    elif personality == "panicker":
        typing_delay = random.uniform(0.8, 2.4)
    elif classification in ("vote_bot", "direct_accusation", "called_bot_or_real"):
        typing_delay = random.uniform(1.2, 3.2)
    else:
        typing_delay = random.uniform(2.0, 4.5)

    second_delay = random.uniform(1.5, 3.0) if message_count > 1 else 0.0
    return round(typing_delay, 2), round(second_delay, 2)


async def build_response_payload(
    req: RespondRequest,
    use_llm: bool = True,
) -> tuple[list[str], str, str, list[int]]:
    """
    Returns (messages, trace_text, trace_source, delays_ms).
    """
    classification = classify_latest_message(req.message, req.botId)
    personality = (req.personality or "").strip().lower() or None

    if not _should_respond(classification, personality):
        trace = _format_trace(
            classification,
            [],
            llm_used=False,
            fallback_used=False,
            delays_ms=[],
            extra="Bot stayed silent to avoid over-talking.",
        )
        return [], trace, "/respond", []

    llm_used = False
    fallback_used = False
    messages: list[str] = []
    trace_source = "/respond"

    if use_llm and config.AI_MODE == "agent":
        agent_payload = await generate_chat_with_agent(req)
        if agent_payload is not None:
            cleaned = sanitize_messages(agent_payload["messages"][:5])
            if cleaned:
                llm_used = True
                messages = cleaned
                trace_source = "/respond:agent"

    if not messages and use_llm and config.AI_MODE == "groq":
        prompt = build_meeting_chat_prompt(req)
        try:
            llm_text = await generate_chat_response(prompt)
        except Exception:
            llm_text = None

        if isinstance(llm_text, str) and llm_text.strip():
            raw_parts = [p.strip() for p in llm_text.split("|") if p.strip()][:5]
            cleaned = sanitize_messages(raw_parts)
            if cleaned:
                llm_used = True
                messages = cleaned
                trace_source = "/respond"

    if not messages:
        fallback_used = True
        messages = generate_human_fallback(
            req.message,
            req.botId,
            req.recentChat,
        )
        trace_source = (
            "/respond:rules_fallback"
            if config.AI_MODE in ("agent", "groq")
            else "/respond"
        )

    messages = _ensure_safe(messages)
    if any(is_bad_bot_output(m) for m in messages):
        fallback_used = True
        messages = _ultra_safe_messages()

    messages = messages[:2]

    delays_ms = calculate_message_delays(messages, classification)
    trace = _format_trace(
        classification,
        messages,
        llm_used=llm_used,
        fallback_used=fallback_used,
        delays_ms=delays_ms,
    )
    return messages, trace, trace_source, delays_ms


@router.post("", response_model=RespondResponse)
async def respond(req: RespondRequest):
    messages, trace_text, trace_source, delays_ms = await build_response_payload(req, use_llm=True)
    respond_flag = bool(messages)
    typing_delay_seconds, second_message_delay_seconds = _delay_seconds(
        classify_latest_message(req.message, req.botId),
        (req.personality or "").strip().lower() or None,
        len(messages),
    )
    if not respond_flag:
        typing_delay_seconds = 0.0
        second_message_delay_seconds = 0.0
    decision = " | ".join(messages) if messages else "silence"
    add_trace(
        req.matchId,
        req.botId,
        "respond",
        decision,
        trace_text,
        trace_source,
        input_data=req.model_dump(by_alias=True),
        output_data={
            "botId": req.botId,
            "respond": respond_flag,
            "messages": messages,
            "typingDelaySeconds": typing_delay_seconds,
            "secondMessageDelaySeconds": second_message_delay_seconds,
            "trace": trace_text,
            "delaysMs": delays_ms,
        },
    )
    return {
        "botId": req.botId,
        "respond": respond_flag,
        "messages": messages,
        "typingDelaySeconds": typing_delay_seconds,
        "secondMessageDelaySeconds": second_message_delay_seconds,
        "trace": trace_text,
        "delaysMs": delays_ms,
    }
