# In-memory state storage for matches and bots
from src.agents.trace_logger import clear_traces

_matches = {}

def register_bot_state(matchId, botId, data):
    m = _matches.setdefault(matchId, {})
    bots = m.setdefault("bots", {})
    bots[botId] = data
    return bots[botId]


def unregister_bot_state(matchId, botId):
    match = _matches.get(matchId)
    if not match:
        return None
    bots = match.get("bots", {})
    removed = bots.pop(botId, None)
    if not bots:
        _matches.pop(matchId, None)
        clear_traces(matchId)
    return removed

def get_bot_state(matchId, botId):
    return _matches.get(matchId, {}).get("bots", {}).get(botId)

def get_match(matchId):
    return _matches.get(matchId, {})

def list_matches():
    return list(_matches.keys())

def clear_match(matchId):
    _matches.pop(matchId, None)
    clear_traces(matchId)
