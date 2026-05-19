from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, RedirectResponse

from src.api.endpoints.decide_action import decide as decide_action_decide
from src.api.endpoints.register_bot import register as register_bot_register
from src.api.endpoints.respond import respond as respond_respond
from src.api.endpoints.respond import build_response_payload
from src.api.endpoints.vote import vote as vote_vote
from src.models.schemas import RegisterRequest, DecideRequest, RespondRequest, VoteRequest
from src.agents.trace_logger import add_trace, clear_traces
from src.core import config
from src.core.state import clear_match

router = APIRouter()


async def _call_register(match_id: str):
    payload = {
        "matchId": match_id,
        "botId": "player_2",
        "wave": 1,
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    return await register_bot_register(RegisterRequest(**payload))


def _rule_based_decide_payload(match_id: str, wave: int, infected_players: list[str], human_players: list[str], nearest_human: str, bot_room: str):
    if len(human_players) == 1:
        mode = "final_hunt"
    elif len(infected_players) >= len(human_players):
        mode = "aggressive_chase"
    elif wave <= 1:
        mode = "stealth_fake_task"
    else:
        mode = "stalk"

    trace_text = ""
    if mode == "stealth_fake_task":
        trace_text = "Early wave. Bot should fake tasks and avoid obvious aggression."
    elif mode == "stalk":
        trace_text = "Mid game: bot should stalk nearby humans."
    else:
        trace_text = f"Mode: {mode} chosen by rule engine."

    return {
        "botId": "player_2",
        "behaviorMode": mode,
        "targetRoom": bot_room,
        "targetPlayer": None,
        "shouldChase": mode in ("final_hunt", "aggressive_chase"),
        "trace": trace_text,
    }


async def _call_decide(match_id: str, wave: int, infected_players: list[str], human_players: list[str], nearest_human: str, bot_room: str):
    payload = {
        "matchId": match_id,
        "phase": "exploration",
        "wave": wave,
        "botId": "player_2",
        "infectedPlayers": infected_players,
        "humanPlayers": human_players,
        "taskProgress": 2,
        "nearestHuman": nearest_human,
        "botRoom": bot_room,
    }
    return await decide_action_decide(DecideRequest(**payload))


async def _call_respond(match_id: str):
    payload = {
        "matchId": match_id,
        "botId": "player_2",
        "message": "player 2 is sus",
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    messages, trace_text, _, delays_ms = await build_response_payload(
        RespondRequest(**payload), use_llm=False
    )
    return {
        "botId": payload["botId"],
        "messages": messages,
        "trace": trace_text,
        "delaysMs": delays_ms,
    }


def _rule_based_vote_payload(match_id: str):
    vote_target = "player_1"
    reason = "No clear accuser; picked random human."
    return {"botId": "player_2", "voteTarget": vote_target, "trace": reason}


async def _call_vote(match_id: str):
    payload = {
        "matchId": match_id,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
        "recentChat": [
            {"sender": "player_1", "text": "player 2 is sus"},
            {"sender": "player_3", "text": "yeah player 2 weird"},
        ],
    }
    return await vote_vote(VoteRequest(**payload))


async def _run_rule_demo(match_id: str):
    steps = []

    register_result = await _call_register(match_id)
    steps.append({"step": "register_bot", "result": register_result})
    add_trace(match_id, "player_2", "register_bot", "deflector | stealth_fake_task", "Registered bot with personality deflector and early stealth behavior.", "/demo/run")

    early_decision = _rule_based_decide_payload(
        match_id=match_id,
        wave=1,
        infected_players=["player_2"],
        human_players=["player_1", "player_3", "player_4"],
        nearest_human="player_3",
        bot_room="Electrical",
    )
    steps.append({"step": "early_decide_action", "result": early_decision})
    add_trace(match_id, "player_2", "decide_action_early", "stealth_fake_task", "Early wave. Bot should fake tasks and avoid obvious aggression.", "/demo/run")

    respond_result = await _call_respond(match_id)
    steps.append({"step": "meeting_respond", "result": respond_result})
    respond_messages = respond_result["messages"] if isinstance(respond_result, dict) else []
    add_trace(match_id, "player_2", "respond", " | ".join(respond_messages) if respond_messages else "silence", "Bot was directly accused, so it denied and defended itself.", "/demo/run")

    vote_result = _rule_based_vote_payload(match_id)
    steps.append({"step": "meeting_vote", "result": vote_result})
    add_trace(match_id, "player_2", "vote", vote_result.get("voteTarget"), vote_result.get("trace", ""), "/demo/run")

    late_decision = _rule_based_decide_payload(
        match_id=match_id,
        wave=3,
        infected_players=["player_2", "player_3"],
        human_players=["player_1", "player_4"],
        nearest_human="player_1",
        bot_room="Generator",
    )
    steps.append({"step": "late_game_decide_action", "result": late_decision})
    add_trace(match_id, "player_2", "decide_action_late", "aggressive_chase", "Infected majority approaching. Increase pressure.", "/demo/run")

    final_decision = _rule_based_decide_payload(
        match_id=match_id,
        wave=3,
        infected_players=["player_2", "player_3", "player_4"],
        human_players=["player_1"],
        nearest_human="player_1",
        bot_room="Exit Gate",
    )
    steps.append({"step": "final_hunt_decide_action", "result": final_decision})
    add_trace(match_id, "player_2", "final_hunt", "final_hunt", "3 infected vs 1 human. Full horror survival mode.", "/demo/run")

    return {
        "matchId": match_id,
        "status": "demo_complete",
        "steps": steps,
        "traceViewerUrl": f"/trace_viewer/{match_id}",
        "traceJsonUrl": f"/trace/{match_id}",
    }


@router.post("/demo/run/{matchId}")
async def run_demo(matchId: str):
    clear_match(matchId)
    return await _run_rule_demo(matchId)


async def _call_agent_decide(match_id: str, wave: int, infected_players: list[str], human_players: list[str], nearest_human: str, bot_room: str):
    payload = {
        "matchId": match_id,
        "phase": "exploration",
        "wave": wave,
        "botId": "player_2",
        "infectedPlayers": infected_players,
        "humanPlayers": human_players,
        "taskProgress": 2,
        "nearestHuman": nearest_human,
        "botRoom": bot_room,
    }
    return await decide_action_decide(DecideRequest(**payload))


async def _call_agent_respond(match_id: str):
    payload = {
        "matchId": match_id,
        "botId": "player_2",
        "message": "player 2 is sus",
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    return await respond_respond(RespondRequest(**payload))


async def _call_agent_vote(match_id: str):
    payload = {
        "matchId": match_id,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
        "recentChat": [
            {"sender": "player_1", "text": "player 2 is sus"},
            {"sender": "player_3", "text": "yeah player 2 weird"},
        ],
    }
    return await vote_vote(VoteRequest(**payload))


def _has_agent_key() -> bool:
    return bool(config.GROQ_API_KEY.strip() or getattr(config, "GEMINI_API_KEY", "").strip())


async def _run_agent_demo(match_id: str):
    steps = []

    register_result = await _call_register(match_id)
    steps.append({"step": "register_bot", "result": register_result})

    early_decision = await _call_agent_decide(
        match_id=match_id,
        wave=1,
        infected_players=["player_2"],
        human_players=["player_1", "player_3", "player_4"],
        nearest_human="player_3",
        bot_room="Electrical",
    )
    steps.append({"step": "early_decide_action", "result": early_decision})

    respond_result = await _call_agent_respond(match_id)
    steps.append({"step": "meeting_respond", "result": respond_result})
    respond_messages = respond_result["messages"] if isinstance(respond_result, dict) else []

    vote_result = await _call_agent_vote(match_id)
    steps.append({"step": "meeting_vote", "result": vote_result})

    late_decision = await _call_agent_decide(
        match_id=match_id,
        wave=3,
        infected_players=["player_2", "player_3"],
        human_players=["player_1", "player_4"],
        nearest_human="player_1",
        bot_room="Generator",
    )
    steps.append({"step": "late_game_decide_action", "result": late_decision})

    final_decision = await _call_agent_decide(
        match_id=match_id,
        wave=3,
        infected_players=["player_2", "player_3", "player_4"],
        human_players=["player_1"],
        nearest_human="player_1",
        bot_room="Exit Gate",
    )
    steps.append({"step": "final_hunt_decide_action", "result": final_decision})

    clear_traces(match_id)
    add_trace(
        match_id,
        "player_2",
        "register_bot",
        f"{register_result.get('personality')} | {register_result.get('behaviorMode')}",
        register_result.get("trace", ""),
        "/register_bot",
    )
    add_trace(
        match_id,
        "player_2",
        "agent_decide_action_early",
        early_decision.get("behaviorMode"),
        early_decision.get("trace", ""),
        "/decide_action:agent",
    )
    add_trace(
        match_id,
        "player_2",
        "agent_respond",
        " | ".join(respond_messages) if respond_messages else "silence",
        respond_result.get("trace", "") if isinstance(respond_result, dict) else "",
        "/respond:agent",
    )
    add_trace(
        match_id,
        "player_2",
        "agent_vote",
        vote_result.get("voteTarget"),
        vote_result.get("trace", ""),
        "/vote:agent",
    )
    add_trace(
        match_id,
        "player_2",
        "agent_decide_action_late",
        late_decision.get("behaviorMode"),
        late_decision.get("trace", ""),
        "/decide_action:agent",
    )
    add_trace(
        match_id,
        "player_2",
        "agent_final_hunt",
        final_decision.get("behaviorMode"),
        final_decision.get("trace", ""),
        "/decide_action:agent",
    )

    return {
        "matchId": match_id,
        "status": "demo_complete",
        "steps": steps,
        "traceViewerUrl": f"/trace_viewer/{match_id}",
        "traceJsonUrl": f"/trace/{match_id}",
    }


@router.post("/demo/clear/{matchId}")
async def clear_demo(matchId: str):
    clear_match(matchId)
    return {"matchId": matchId, "status": "cleared"}


@router.post("/demo/quick/{matchId}")
async def quick_demo(matchId: str):
    clear_match(matchId)
    await _run_rule_demo(matchId)
    fresh = int(datetime.now(timezone.utc).timestamp())
    return RedirectResponse(url=f"/trace_viewer/{matchId}?fresh={fresh}", status_code=303)


@router.post("/demo/agent_quick/{matchId}")
async def agent_quick_demo(matchId: str):
    if config.AI_MODE != "agent":
        return PlainTextResponse("Agent mode is not enabled. Set AI_MODE=agent.", status_code=400)
    if not _has_agent_key():
        return PlainTextResponse("Agent mode enabled but no LLM key configured.", status_code=400)

    clear_match(matchId)
    await _run_agent_demo(matchId)
    fresh = int(datetime.now(timezone.utc).timestamp())
    return RedirectResponse(url=f"/trace_viewer/{matchId}?fresh={fresh}", status_code=303)
