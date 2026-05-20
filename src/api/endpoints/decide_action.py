from fastapi import APIRouter
from src.models.schemas import DecideRequest, DecideActionResponse
from src.agents.behavior_director import BehaviorDirector
from src.agents.agentic_decision_engine import validate_decide_behavior_with_agent
from src.agents.trace_logger import add_trace
from src.core import config
from src.core.state import get_bot_state

router = APIRouter()
behavior = BehaviorDirector()


def _rule_based_decision(req: DecideRequest) -> tuple[dict, str]:
    infected_count = len(req.infectedPlayers)
    human_count = len(req.humanPlayers)
    bot_state = get_bot_state(req.matchId, req.botId) or {}
    valid_target = req.nearestHuman if req.nearestHuman in req.humanPlayers else (req.humanPlayers[0] if req.humanPlayers else None)
    target_room = req.nearestHumanRoom or req.botRoom or bot_state.get("botRoom")

    if req.isFinalChase or len(req.humanPlayers) == 1:
        mode = "final_hunt"
    elif infected_count < human_count:
        if req.wave >= 2:
            mode = "stalk"
        else:
            mode = "stealth_fake_task"
    else:
        mode = "aggressive_chase"

    should_chase = mode in ("final_hunt", "aggressive_chase") and bool(valid_target)
    if req.isFinalChase or len(req.humanPlayers) == 1:
        should_chase = True

    next_delay = 20 + ((req.wave * 3 + req.cycle + len(req.alivePlayers)) % 11)
    trace_text = ""
    if mode == "stealth_fake_task":
        trace_text = "Early game: fake tasks and avoid obvious aggression."
    elif mode == "stalk":
        trace_text = "Mid game: stalk nearest human but avoid obvious chase."
    elif mode == "aggressive_chase":
        trace_text = "Numbers favor infection, so pressure the humans."
    elif mode == "final_hunt":
        trace_text = "Final chase: commit to the last human target."
    else:
        trace_text = f"Mode: {mode} chosen by rule engine."

    decision = {
        "botId": req.botId,
        "behaviorMode": mode,
        "targetRoom": target_room,
        "targetPlayer": valid_target,
        "shouldChase": should_chase,
        "nextDecisionInSeconds": next_delay,
        "trace": trace_text,
    }
    return decision, trace_text


@router.post("", response_model=DecideActionResponse)
async def decide(req: DecideRequest):
    agent_decision, validation_error = await validate_decide_behavior_with_agent(req)
    agent_llm_used = bool(agent_decision and agent_decision.get("llmDebug", {}).get("llmUsed"))
    if agent_decision is not None and agent_llm_used:
        llm_debug = agent_decision.get("llmDebug", {}) or {}
        decision = {
            "botId": req.botId,
            **agent_decision,
            "trace": agent_decision["reason"],
        }
        decision["trace"] = " | ".join(
            part
            for part in [
                f"reason={agent_decision['reason']}",
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
            "decide_action",
            agent_decision["behaviorMode"],
            decision["trace"],
            "/decide_action:agent",
            input_data=req.model_dump(by_alias=True),
            output_data=decision,
        )
        return decision

    if agent_decision is not None and not agent_llm_used:
        llm_debug = agent_decision.get("llmDebug", {}) or {}
        fallback_reason = llm_debug.get("fallbackReason") or validation_error or agent_decision.get("reason", "llm_failed")
        add_trace(
            req.matchId,
            req.botId,
            "agent_decide_action_failed",
            "rules_fallback",
            f"fallback_reason={fallback_reason} | stage={llm_debug.get('stage', '')} | statusCode={llm_debug.get('statusCode', '')}",
            "/decide_action:agent_validation_failed",
        )

    if config.AI_MODE == "agent" and validation_error:
        add_trace(
            req.matchId,
            req.botId,
            "agent_decide_action_failed",
            "rules_fallback",
            f"fallback_reason={validation_error}",
            "/decide_action:agent_validation_failed",
        )

    decision, trace_text = _rule_based_decision(req)
    trace_source = "/decide_action:rules_fallback" if config.AI_MODE == "agent" else "/decide_action"
    add_trace(
        req.matchId,
        req.botId,
        "decide_action",
        decision["behaviorMode"],
        trace_text,
        trace_source,
        input_data=req.model_dump(by_alias=True),
        output_data=decision,
    )
    return decision
