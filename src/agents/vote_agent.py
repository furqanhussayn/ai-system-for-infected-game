class VoteAgent:
    def choose_vote(self, botId, state):
        # simple heuristic
        alive = state.get("alivePlayers", []) if isinstance(state, dict) else []
        target = alive[0] if alive else None
        reason = "heuristic: pick first alive"
        return target, reason
