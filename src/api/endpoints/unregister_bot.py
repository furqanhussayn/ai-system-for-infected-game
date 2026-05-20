from fastapi import APIRouter
from src.models.schemas import UnregisterBotRequest, UnregisterBotResponse
from src.core.state import unregister_bot_state
from src.agents.trace_logger import add_trace

router = APIRouter()

@router.post("", response_model=UnregisterBotResponse)
async def unregister(req: UnregisterBotRequest):
    removed = unregister_bot_state(req.matchId, req.botId)
    if removed is None:
        trace_text = f"Bot {req.botId} was already absent or removed."
    else:
        trace_text = f"Bot {req.botId} unregistered after {req.reason or 'unknown reason'}."
    add_trace(
        req.matchId,
        req.botId,
        "unregister_bot",
        {"reason": req.reason, "removed": bool(removed)},
        trace_text,
        "/unregister_bot",
        input_data=req.model_dump(by_alias=True),
        output_data={"ok": True, "botId": req.botId, "trace": trace_text},
    )
    return {"ok": True, "botId": req.botId, "trace": trace_text}
