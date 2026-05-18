class StateAgent:
    def snapshot(self, register_req):
        # return minimal structured state used by other agents
        return {
            "phase": getattr(register_req, "phase", "exploration"),
            "wave": register_req.get("wave", 0) if isinstance(register_req, dict) else getattr(register_req, "wave", 0),
            "alive": getattr(register_req, "alivePlayers", [])
        }
