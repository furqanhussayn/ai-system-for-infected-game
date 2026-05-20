from fastapi import APIRouter
from src.models.schemas import VoteRequest, VoteResponse
from src.agents.vote_agent import VoteAgent
from src.agents.agentic_decision_engine import decide_vote_with_agent
from src.agents.trace_logger import add_trace
from src.core import config
import random

router = APIRouter()
voter = VoteAgent()


def _message_text(item) -> str:
    if hasattr(item, "text"):
        return str(getattr(item, "text", ""))
    return str(item.get("text", ""))


def _message_sender(item) -> str:
    if hasattr(item, "sender"):
        return str(getattr(item, "sender", ""))
    return str(item.get("sender", ""))


def _rule_based_vote(req: VoteRequest) -> tuple[str | None, str]:
    humans = [player for player in req.humanPlayers if player in req.alivePlayers and player != req.botId]
    if not humans:
        humans = [player for player in req.alivePlayers if player != req.botId and player not in req.infectedPlayers]

    accuser = None
    for msg in req.recentChat:
        sender = _message_sender(msg)
        text = _message_text(msg).lower()
        if sender == req.botId:
            continue
        if sender and sender in humans:
            if any(marker in text for marker in (req.botId.lower(), req.botId.replace("_", " ").lower(), "sus", "weird", "following", "chasing", "why is player", "near body", "near gen", "near generator")):
                accuser = sender
                break

    if accuser:
        return accuser, f"{accuser} accused the bot first."

    if humans:
        chosen = random.choice(humans)
        return chosen, "No clear accuser; picked a random human."

    return None, "No valid human vote target."


@router.post("", response_model=VoteResponse)
async def vote(req: VoteRequest):
    agent_vote = await decide_vote_with_agent(req)
    agent_llm_used = bool(agent_vote and agent_vote.get("llmDebug", {}).get("llmUsed"))
    if agent_vote is not None and agent_llm_used:
        llm_debug = agent_vote.get("llmDebug", {}) or {}
        trace_text = " | ".join(
            part
            for part in [
                f"reason={agent_vote['reason']}",
                f"llm_attempted={llm_debug.get('llmAttempted', False)}",
                f"llm_used={llm_debug.get('llmUsed', False)}",
                f"fallback_reason={llm_debug.get('fallbackReason', '')}",
                f"provider={llm_debug.get('provider', '')}",
                f"model={llm_debug.get('model', '')}",
                f"stage={llm_debug.get('stage', '')}",
                f"statusCode={llm_debug.get('statusCode', '')}",
                f"latencyMs={llm_debug.get('latencyMs', 0)}",
            ]
            if part is not None
        )
        add_trace(
            req.matchId,
            req.botId,
            "vote",
            agent_vote["voteTarget"],
            trace_text,
            "/vote:agent",
            input_data=req.model_dump(by_alias=True),
            output_data={"botId": req.botId, "voteTarget": agent_vote["voteTarget"], "reason": agent_vote["reason"], "trace": trace_text},
        )
        return {"botId": req.botId, "voteTarget": agent_vote["voteTarget"], "reason": agent_vote["reason"], "trace": trace_text}

    if agent_vote is not None and not agent_llm_used:
        llm_debug = agent_vote.get("llmDebug", {}) or {}
        failure_reason = llm_debug.get("fallbackReason") or agent_vote.get("reason", "llm_failed")
        add_trace(
            req.matchId,
            req.botId,
            "agent_vote_failed",
            "rules_fallback",
            f"fallback_reason={failure_reason} | stage={llm_debug.get('stage', '')} | statusCode={llm_debug.get('statusCode', '')}",
            "/vote:agent_validation_failed",
            input_data=req.model_dump(by_alias=True),
            output_data={"botId": req.botId, "voteTarget": agent_vote.get("voteTarget"), "reason": agent_vote.get("reason"), "trace": failure_reason},
        )

    vote_target, reason = _rule_based_vote(req)
    trace_source = "/vote:rules_fallback" if config.AI_MODE == "agent" else "/vote"

    add_trace(
        req.matchId,
        req.botId,
        "vote",
        vote_target,
        reason,
        trace_source,
        input_data=req.model_dump(by_alias=True),
        output_data={"botId": req.botId, "voteTarget": vote_target, "reason": reason, "trace": reason},
    )
    return {"botId": req.botId, "voteTarget": vote_target, "reason": reason, "trace": reason}
