from fastapi import APIRouter
from src.models.schemas import RegisterRequest, RegisterResponse
from src.agents.trace_logger import add_trace
from src.agents.behavior_director import BehaviorDirector
from src.agents.state_agent import StateAgent
from src.core.state import get_bot_state, register_bot_state

router = APIRouter()
state_agent = StateAgent()
behavior = BehaviorDirector()


@router.post("", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    existing = get_bot_state(req.matchId, req.botId) or {}
    personality = existing.get("personality") or behavior.assign_personality(req.botId, req.wave, req.infectedPlayers)
    mode = existing.get("behaviorMode") or behavior.initial_mode(personality, state_agent.snapshot(req))
    trace_text = (
        f"Registered bot with personality {personality} and early {mode} behavior."
        if not existing
        else f"Updated bot state for {req.botId} with personality {personality} and behavior {mode}."
    )
    bot_obj = {
        "botId": req.botId,
        "personality": personality,
        "behaviorMode": mode,
        "matchId": req.matchId,
        "wave": req.wave,
        "botName": req.botName,
        "phase": req.phase,
        "cycle": req.cycle,
        "taskProgress": req.taskProgress,
        "alivePlayers": req.alivePlayers,
        "humanPlayers": req.humanPlayers,
        "infectedPlayers": req.infectedPlayers,
    }
    register_bot_state(req.matchId, req.botId, bot_obj)
    add_trace(
        req.matchId,
        req.botId,
        "register_bot",
        f"{personality} | {mode}",
        trace_text,
        "/register_bot",
        input_data=req.model_dump(by_alias=True),
        output_data={"ok": True, "botId": req.botId, "personality": personality, "behaviorMode": mode, "trace": trace_text},
    )
    return {"ok": True, "botId": req.botId, "personality": personality, "behaviorMode": mode, "trace": trace_text}
