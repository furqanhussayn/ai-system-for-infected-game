from fastapi import APIRouter
from src.models.schemas import RegisterRequest, RegisterResponse
from src.agents.trace_logger import add_trace
from src.agents.behavior_director import BehaviorDirector
from src.agents.state_agent import StateAgent
from src.core.state import register_bot_state

router = APIRouter()
state_agent = StateAgent()
behavior = BehaviorDirector()


@router.post("", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    # rule-based assignment
    personality = behavior.assign_personality(req.botId, req.wave, req.infectedPlayers)
    mode = behavior.initial_mode(personality, state_agent.snapshot(req))
    trace_text = f"Registered bot with personality {personality} and early {mode} behavior."
    # store in memory
    bot_obj = {
        "botId": req.botId,
        "personality": personality,
        "behaviorMode": mode,
        "matchId": req.matchId,
        "wave": req.wave,
    }
    register_bot_state(req.matchId, req.botId, bot_obj)
    add_trace(
        req.matchId,
        req.botId,
        "register_bot",
        f"{personality} | {mode}",
        trace_text,
        "/register_bot",
    )
    return {"botId": req.botId, "personality": personality, "behaviorMode": mode, "trace": trace_text}
