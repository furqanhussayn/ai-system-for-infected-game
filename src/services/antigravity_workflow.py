from time import time
from src.core.config import AI_CALL_MIN_INTERVAL

# in-memory simple gating for demo; keyed by (botId,event)
_last_calls = {}

def allowed_call(botId: str, event: str, force: bool = False) -> bool:
    key = (botId, event)
    now = time()
    last = _last_calls.get(key, 0)
    if force:
        _last_calls[key] = now
        return True
    if now - last >= AI_CALL_MIN_INTERVAL:
        _last_calls[key] = now
        return True
    return False
