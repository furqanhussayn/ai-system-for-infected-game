import random
from src.services.antigravity_workflow import allowed_call

class BehaviorDirector:
    PERSONALITIES = ["quiet","deflector","framer","panicker","crowd_follower"]

    def assign_personality(self, botId, wave, infectedPlayers):
        return random.choice(self.PERSONALITIES)

    def initial_mode(self, personality, state):
        return "stealth_fake_task"

    def decide_action(self, botId, state):
        event = "behavior_update"
        if not allowed_call(botId, event):
            return {"behaviorMode": state.get("behaviorMode", "stealth_fake_task"), "targetPlayer": None, "targetRoom": None, "trace": "cached decision (rate limited)"}
        infected = state.get("infectedCount", len(state.get("infectedPlayers", [])))
        wave = state.get("wave", 0)
        if infected >= 3 and infected > (len(state.get("alive", [])) // 2):
            mode = "aggressive_chase"
        elif wave > 2:
            mode = "stalk_mode"
        else:
            mode = "stealth_fake_task"
        targetRoom = None
        if mode == "stealth_fake_task":
            targetRoom = random.choice(["Electrical", "Generator", "Maintenance"])
        return {"behaviorMode": mode, "targetPlayer": None, "targetRoom": targetRoom, "trace": "computed decision"}
