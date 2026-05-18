from fastapi import APIRouter
from src.models.schemas import VoteRequest, VoteResponse
from src.agents.vote_agent import VoteAgent
from src.agents.agentic_decision_engine import decide_vote_with_agent
from src.agents.trace_logger import add_trace
from src.core import config
import random

router = APIRouter()
voter = VoteAgent()


def _rule_based_vote(req: VoteRequest) -> tuple[str | None, str]:
    alive = [p for p in req.alivePlayers if p != req.botId]
    known_infected = set(req.infectedPlayers)
    candidates = [p for p in alive if p not in known_infected]

    accusers = []
    for msg in req.recentChat:
        if req.botId in msg.get("text", "") or ("player" in msg.get("text", "") and msg.get("sender")):
            text = msg.get("text", "").lower()
            if "sus" in text or req.botId.lower() in text:
                accusers.append(msg.get("sender"))

    vote_target = None
    reason = ""
    if accusers:
        for a in accusers:
            if a != req.botId and a in candidates:
                vote_target = a
                reason = f"{a} accused the bot in chat."
                break

    if not vote_target:
        if candidates:
            vote_target = random.choice(candidates)
            reason = "No clear accuser; picked random human."
        else:
            vote_target = alive[0] if alive else None
            reason = "Fallback pick"

    return vote_target, reason


@router.post("", response_model=VoteResponse)
async def vote(req: VoteRequest):
    agent_vote = await decide_vote_with_agent(req)
    if agent_vote is not None:
        add_trace(
            req.matchId,
            req.botId,
            "vote",
            agent_vote["voteTarget"],
            agent_vote["reason"],
            "/vote:agent",
        )
        return {"botId": req.botId, "voteTarget": agent_vote["voteTarget"], "trace": agent_vote["reason"]}

    vote_target, reason = _rule_based_vote(req)
    trace_source = "/vote:rules_fallback" if config.AI_MODE == "agent" else "/vote"

    add_trace(
        req.matchId,
        req.botId,
        "vote",
        vote_target,
        reason,
        trace_source,
    )
    return {"botId": req.botId, "voteTarget": vote_target, "trace": reason}
