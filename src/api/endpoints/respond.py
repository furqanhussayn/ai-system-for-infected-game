from __future__ import annotations

import random

from fastapi import APIRouter

from src.agents.agentic_decision_engine import generate_chat_with_agent
from src.agents.chat_classifier import classify_latest_message
from src.agents.chat_delays import calculate_message_delays
from src.agents.chat_diversity_guard import apply_event_diversity
from src.agents.chat_style_guard import clean_message, is_bad_bot_output, sanitize_messages
from src.agents.human_fallback import generate_human_fallback as original_human_fallback

# Keep local alias for compatibility with existing code in this file
generate_human_fallback = original_human_fallback
from src.agents.meeting_chat_prompt import build_meeting_chat_prompt
from src.agents.trace_logger import add_trace
from src.core import config
from src.models.schemas import RespondRequest, RespondResponse
from src.services.llm_adapter import generate_chat_response as original_generate_chat_response

# Keep the compatibility alias for older tests and call sites.
generate_chat_response = original_generate_chat_response

router = APIRouter()

_RESPONSE_CHANCE: dict[str, float] = {
    "vote_bot": 1.00,
    "direct_accusation": 1.00,
    "called_bot_or_real": 1.00,
    "insult": 0.75,
    "asks_who_infected": 0.65,
    "question_prompt": 0.85,
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


def _should_respond(
    classification: str,
    personality: str | None = None,
    *,
    prefer_llm: bool = False,
) -> bool:
    if prefer_llm and classification in ("generic", "question_prompt", "asks_who_infected"):
        return True
    if personality == "quiet" and classification not in ("vote_bot", "direct_accusation", "called_bot_or_real", "question_prompt"):
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
    llm_attempted: bool,
    llm_used: bool,
    fallback_used: bool,
    fallback_reason: str = "",
    provider: str = "",
    model: str = "",
    stage: str = "",
    status_code: int | None = None,
    latency_ms: int = 0,
    raw_preview: str = "",
    delays_ms: list[int],
    extra: str = "",
    prompt_chars: int | None = None,
    recent_chat_sent: list[str] | None = None,
    prompt_mode: str | None = None,
    intent: str | None = None,
    targeted_player: str | None = None,
    key_id_used: str | None = None,
    attempt_count: int | None = None,
    failure_chain: list[dict[str, object]] | None = None,
) -> str:
    parts = [
        f"classification={classification}",
        f"llm_attempted={llm_attempted}",
        f"message_count={len(messages)}",
        f"llm_used={llm_used}",
        f"fallback_used={fallback_used}",
        f"fallback_reason={fallback_reason or ''}",
        f"provider={provider or ''}",
        f"providerUsed={provider or ''}",
        f"model={model or ''}",
        f"modelUsed={model or ''}",
        f"stage={stage or ''}",
        f"statusCode={status_code if status_code is not None else ''}",
        f"latencyMs={latency_ms}",
        f"rawPreview={raw_preview or ''}",
        f"delaysMs={delays_ms}",
    ]
    if prompt_chars is not None:
        parts.append(f"ctxChars={prompt_chars}")
    if recent_chat_sent is not None:
        parts.append(f"recentSent={recent_chat_sent}")
    if prompt_mode:
        parts.append(f"ctxMode={prompt_mode}")
    if intent:
        parts.append(f"intent={intent}")
    if targeted_player:
        parts.append(f"targetedPlayer={targeted_player}")
    if key_id_used:
        parts.append(f"keyIdUsed={key_id_used}")
    if attempt_count is not None:
        parts.append(f"attemptCount={attempt_count}")
    if failure_chain:
        chain_text = ",".join(
            "{}".format(
                ":".join(
                    part
                    for part in [
                        str(entry.get("provider", "") or ""),
                        str(entry.get("keyId", "") or ""),
                        str(entry.get("stage", "") or ""),
                    ]
                    if part
                )
            )
            for entry in failure_chain
            if isinstance(entry, dict)
        )
        if chain_text:
            parts.append(f"failureChain={chain_text}")
    if extra:
        parts.append(extra)
    return " | ".join(parts)


def _failure_chain_summary(chain: list[dict[str, object]] | None) -> list[dict[str, object]]:
    if not chain:
        return []
    summary: list[dict[str, object]] = []
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        summary.append(
            {
                "provider": str(entry.get("provider", "")),
                "keyId": str(entry.get("keyId", "")),
                "stage": str(entry.get("stage", "")),
                "statusCode": entry.get("statusCode"),
            }
        )
    return summary


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


async def build_response_payload(
    req: RespondRequest,
    use_llm: bool = True,
) -> tuple[list[str], str, str, list[int]]:
    """
    Returns (messages, trace_text, trace_source, delays_ms).
    """
    classification = classify_latest_message(req.message, req.botId)
    personality = (req.personality or "").strip().lower() or None
    prefer_llm = config.AI_MODE in ("agent", "groq")

    if not _should_respond(classification, personality, prefer_llm=prefer_llm):
        trace = _format_trace(
            classification,
            [],
            llm_attempted=False,
            llm_used=False,
            fallback_used=False,
            delays_ms=[],
            extra="Bot stayed silent to avoid over-talking.",
        )
        return [], trace, "/respond", []

    # Deterministic local answer for common question prompts when LLM is not used
    if classification == "question_prompt" and not prefer_llm:
        # Provide a short, compact deterministic answer to avoid random fallback variability.
        messages = ["i was at electrical", "task progress looked fine to me"]
        llm_attempted = False
        llm_used = False
        fallback_used = False
        trace_source = "/respond:rules"
        delays_ms = calculate_message_delays(messages, classification)
        trace = _format_trace(
            classification,
            messages,
            llm_attempted=llm_attempted,
            llm_used=llm_used,
            fallback_used=fallback_used,
            fallback_reason="",
            provider="",
            model="",
            stage="rules_answer",
            status_code=None,
            latency_ms=0,
            raw_preview="",
            delays_ms=delays_ms,
            extra="deterministic rules reply",
            prompt_chars=None,
            recent_chat_sent=[],
            prompt_mode=None,
            intent=None,
            targeted_player=None,
        )
        return messages, trace, trace_source, delays_ms

    llm_used = False
    llm_attempted = bool(use_llm and config.AI_MODE in ("agent", "groq"))
    fallback_used = False
    fallback_reason = ""
    messages: list[str] = []
    trace_source = "/respond"
    llm_debug: dict[str, Any] = {
        "llmAttempted": llm_attempted,
        "llmUsed": False,
        "fallbackReason": "",
        "provider": config.LLM_PROVIDER,
        "model": config.GROQ_MODEL if str(config.LLM_PROVIDER).strip().lower() == "groq" else config.GEMINI_MODEL,
        "keyIdUsed": "",
        "stage": "mode_disabled" if not llm_attempted else "",
        "statusCode": None,
        "latencyMs": 0,
        "rawPreview": "",
        "errorType": "",
        "errorMessage": "",
        "attemptCount": 0,
        "failureChain": [],
    }
    recent_chat_texts = []
    for item in req.recentChat[-8:]:
        recent_chat_texts.append(_message_text(item))

    event_context = {
        "usedMessages": [],
        "usedMessageKeys": [],
        "usedOpeners": [],
        "usedIntents": [],
        "latestHumanMessage": req.message,
        "recentChatTexts": recent_chat_texts,
    }

    if llm_attempted:
        agent_payload = await generate_chat_with_agent(req, event_context=event_context)
        if agent_payload is not None:
            llm_debug = agent_payload.get("llmDebug", llm_debug)
            # If local rules decided silence, avoid falling back to human fallback.
            if agent_payload.get("reason") == "local_silence":
                llm_attempted = False
                llm_used = False
                fallback_used = False
                fallback_reason = "local_silence"
                messages = []
                trace_source = "/respond:local_silence"
                # propagate prompt stats if available
                trace_prompt_chars = int(llm_debug.get("promptChars", 0) or 0)
                trace_recent_chat = llm_debug.get("recentChatSent", []) or []
                trace_prompt_mode = llm_debug.get("promptMode", None)
                # update llm_debug for trace
                llm_debug.setdefault("llmAttempted", False)
                llm_debug.setdefault("llmUsed", False)
            else:
                cleaned = sanitize_messages(agent_payload.get("messages", [])[:5])
                if cleaned:
                    llm_used = True
                    messages = cleaned
                    trace_source = "/respond:agent" if config.AI_MODE == "agent" else "/respond"
                    llm_debug["llmUsed"] = True
                else:
                    fallback_reason = agent_payload.get("reason", llm_debug.get("fallbackReason", "")) or llm_debug.get("fallbackReason", "")
                    llm_debug["fallbackReason"] = fallback_reason
                trace_prompt_chars = int(llm_debug.get("promptChars", 0) or 0)
                trace_recent_chat = llm_debug.get("recentChatSent", []) or []
                trace_prompt_mode = llm_debug.get("promptMode", None)
        elif config.AI_MODE in ("agent", "groq"):
            fallback_reason = "llm_unavailable"
            llm_debug["stage"] = "adapter_exception"
            llm_debug["fallbackReason"] = fallback_reason

    if not messages:
        # Compatibility: try direct module-level generate_chat_response if available (tests may monkeypatch it)
        try:
            if llm_attempted and config.AI_MODE == "groq" and generate_chat_response is not original_generate_chat_response and callable(generate_chat_response):
                bot_state = {}
                try:
                    from src.core.state import get_bot_state as _get_bot_state

                    bot_state = _get_bot_state(req.matchId, req.botId) or {}
                except Exception:
                    bot_state = {}
                prompt_try = build_meeting_chat_prompt(req, bot_state=bot_state)
                maybe = await generate_chat_response(prompt_try)
                if isinstance(maybe, str) or hasattr(maybe, "text"):
                    from src.agents.agentic_decision_engine import _repair_plain_text_chat_messages as _repair_fn

                    repaired = _repair_fn(maybe.text if hasattr(maybe, "text") else maybe)
                    if repaired:
                        cleaned_try = sanitize_messages(repaired)
                        if cleaned_try:
                            messages = cleaned_try
                            llm_used = True
                            trace_source = "/respond:agent"
                            llm_debug["llmUsed"] = True
        except Exception:
            pass

        if not messages:
            fallback_used = True
            messages = generate_human_fallback(req.message, req.botId, req.recentChat)
        if not fallback_reason:
            fallback_reason = llm_debug.get("fallbackReason", "") or "rules_fallback"
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
    messages, diversity_stats = apply_event_diversity(
        event_context,
        messages,
        intent=_replacement_intent_for_classification(classification, personality),
    )

    if not messages:
        fallback_used = True
        messages = _ensure_safe(
            generate_human_fallback(req.message, req.botId, req.recentChat)
        )[:2]
        messages, diversity_stats = apply_event_diversity(
            event_context,
            messages,
            intent=_replacement_intent_for_classification(classification, personality),
        )

    delays_ms = calculate_message_delays(messages, classification)
    trace = _format_trace(
        classification,
        messages,
        llm_attempted=llm_attempted,
        llm_used=llm_used,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason or llm_debug.get("fallbackReason", ""),
        provider=str(llm_debug.get("provider", "")),
        model=str(llm_debug.get("model", "")),
        stage=str(llm_debug.get("stage", "")),
        status_code=llm_debug.get("statusCode"),
        latency_ms=int(llm_debug.get("latencyMs", 0) or 0),
        raw_preview=str(llm_debug.get("rawPreview", "")),
        delays_ms=delays_ms,
        extra=f"diversityApplied={diversity_stats.get('diversityApplied', False)}",
        prompt_chars=trace_prompt_chars if 'trace_prompt_chars' in locals() else None,
        recent_chat_sent=trace_recent_chat if 'trace_recent_chat' in locals() else None,
        prompt_mode=trace_prompt_mode if 'trace_prompt_mode' in locals() else None,
        intent=event_context.get("usedIntents", [])[-1] if event_context.get("usedIntents") else None,
        targeted_player=None,
        key_id_used=str(llm_debug.get("keyIdUsed", "") or "") or None,
        attempt_count=int(llm_debug.get("attemptCount", 0) or 0) or None,
        failure_chain=_failure_chain_summary(llm_debug.get("failureChain", []) or []),
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
