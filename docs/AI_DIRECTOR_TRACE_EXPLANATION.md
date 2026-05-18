# AI Director Trace Explanation — THE INFECTED

Each trace card in `/trace_viewer/{matchId}` represents one agent decision.  
This document explains what each card type means, what triggered it, and why it matters in gameplay.

---

## Trace Card Type: `register_bot`

### When It Fires
At match start, when Unity sends the first `POST /register_bot` for an infected bot.

### Input State
```json
{
  "matchId": "ROOM_XYZ",
  "botId": "player_2",
  "wave": 1,
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "infectedPlayers": ["player_2"]
}
```

### Agent Decision
- **StateAgent** parses `alivePlayers` and `wave` into a normalized snapshot
- **BehaviorDirector** randomly assigns a personality from: `quiet`, `deflector`, `framer`, `panicker`, `crowd_follower`
- **BehaviorDirector** sets initial behavior mode to `stealth_fake_task`
- Bot state stored in memory: `personality`, `behaviorMode`, `matchId`, `wave`

### Output Action
```json
{
  "botId": "player_2",
  "personality": "deflector",
  "behaviorMode": "stealth_fake_task",
  "trace": "Registered bot with personality deflector and early stealth_fake_task behavior."
}
```

### Why It Matters in Gameplay
The personality assigned at registration persists for the entire match. It determines:
- How often the bot responds in chat (response rate per personality)
- Which template phrases the bot uses in meetings
- How the Groq prompt frames the bot's chat style

A `deflector` bot will say things like "nahhh i didnt do anything" and "bro why me tho??" — deflecting accusations. A `panicker` bot will use more frantic, caps-lock responses. This creates distinct, recognizable bot archetypes that real players will notice.

---

## Trace Card Type: `decide_action_early`

### When It Fires
During the early game (wave ≤ 1, low infected count), when Unity calls `POST /decide_action`.

### Input State
```json
{
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "phase": "exploration",
  "wave": 1,
  "infectedPlayers": ["player_2"],
  "humanPlayers": ["player_1", "player_3", "player_4"],
  "taskProgress": 2,
  "nearestHuman": "player_3",
  "botRoom": "Electrical"
}
```

### Agent Decision
The **BehaviorDirector** applies the rule engine:
```
humanPlayers.length = 3, infectedPlayers.length = 1
wave = 1

→ wave <= 1: stealth_fake_task
→ targetRoom: random(["Electrical", "Generator", "Maintenance"])
→ shouldChase: False
```

### Output Action
```json
{
  "botId": "player_2",
  "behaviorMode": "stealth_fake_task",
  "targetRoom": "Electrical",
  "targetPlayer": null,
  "shouldChase": false,
  "trace": "Early wave. Bot should fake tasks and avoid obvious aggression."
}
```

### Why It Matters in Gameplay
Early game stealth is critical for social deduction. If the infected bot attacks immediately, humans can identify and vote it out before it spreads. The `stealth_fake_task` mode instructs Unity to navigate the bot to a task room and play a task animation — indistinguishable from a real player doing tasks. This buys time for the infection to spread naturally.

---

## Trace Card Type: `respond`

### When It Fires
During an emergency meeting, when Unity calls `POST /respond` after a player sends a chat message.

### Input State
```json
{
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "message": "player 2 is sus",
  "recentChat": [
    {"sender": "player_1", "text": "player 2 is sus"}
  ],
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "infectedPlayers": ["player_2"]
}
```

### Agent Decision
The **ChatAgent** pipeline:
1. `_is_direct_mention()` detects that `"player 2"` appears in the message → respond = True (bypasses rate check)
2. `_rule_based_messages("deflector")` selects a denial/deflect template
3. If `AI_MODE=groq`: `_build_prompt()` constructs a hardened system prompt → Groq API → safety filter
4. Safety filter checks for forbidden phrases: `["ai", "model", "groq", "i am infected", ...]`
5. Passes safety check → return response

### Output Action
```json
{
  "botId": "player_2",
  "messages": ["nahhh i didnt do anything", "bro why me tho??"],
  "trace": "Bot was directly accused, so it denied and defended itself."
}
```

### Why It Matters in Gameplay
The `messages` array is rendered directly in Unity's chat UI. A convincing, human-like denial confuses real players during the vote. The multi-message format (two short messages separated by `|`) mimics how real players type in short bursts rather than long paragraphs. The personality-specific templates ensure different bots have different "voices" — making the deception more believable.

The safety filter ensures the bot **never accidentally reveals** that it's an AI, that it's infected, or that it knows game internals — preserving game integrity.

---

## Trace Card Type: `vote`

### When It Fires
At the end of an emergency meeting, when Unity calls `POST /vote` to get the bot's nomination.

### Input State
```json
{
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "infectedPlayers": ["player_2"],
  "recentChat": [
    {"sender": "player_1", "text": "player 2 is sus"},
    {"sender": "player_3", "text": "yeah player 2 weird"}
  ]
}
```

### Agent Decision
The **VoteAgent** pipeline:
1. Build candidate list: `alive - self - known_infected` → `["player_1", "player_3", "player_4"]`
2. Scan `recentChat` for accusers: messages containing `botId` or "sus"
   - `player_1` accused → add to accusers list
3. Counter-vote: `player_1` is in candidates → `voteTarget = "player_1"`
4. Reason: `"player_1 accused the bot in chat."`

### Output Action
```json
{
  "botId": "player_2",
  "voteTarget": "player_1",
  "trace": "player_1 accused the bot in chat."
}
```

### Why It Matters in Gameplay
Strategic voting is what makes the infected team dangerous. Instead of randomly eliminating players (which would be obvious and ineffective), the bot targets its most active accuser. This:
- Removes the player most likely to correctly identify the bot
- Creates plausible cover ("they were acting weird too")
- Mimics how real infected players vote in human games

The vote result is sent to Unity which updates the meeting UI and tallies votes.

---

## Trace Card Type: `decide_action_late`

### When It Fires
Mid-to-late game when infected players now equal or outnumber humans. Unity calls `POST /decide_action` at wave 3.

### Input State
```json
{
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "phase": "exploration",
  "wave": 3,
  "infectedPlayers": ["player_2", "player_3"],
  "humanPlayers": ["player_1", "player_4"],
  "taskProgress": 5,
  "nearestHuman": "player_1",
  "botRoom": "Generator"
}
```

### Agent Decision
The **BehaviorDirector** re-evaluates:
```
infectedCount = 2, humanCount = 2
infectedCount >= humanCount → aggressive_chase
shouldChase = True
targetRoom = None (chase, don't navigate to task)
```

### Output Action
```json
{
  "botId": "player_2",
  "behaviorMode": "aggressive_chase",
  "targetRoom": null,
  "targetPlayer": null,
  "shouldChase": true,
  "trace": "Mode: aggressive_chase chosen by rule engine."
}
```

### Why It Matters in Gameplay
When infected reach parity with humans, the game enters its horror climax. `aggressive_chase` instructs Unity to:
- Enable chase animation and physics
- Remove task-faking behavior
- Pursue nearby humans
- Trigger horror SFX and camera effects

The `shouldChase: true` flag is the direct signal to Unity's NavMesh agent to switch from task-navigation mode to pursuit mode. The timing of this escalation — based on actual game state ratios — is what creates a natural, escalating horror experience rather than a scripted one.

---

## Trace Card Type: `final_hunt`

### When It Fires
End-game when only 1 human remains. Unity calls `POST /decide_action`.

### Input State
```json
{
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "phase": "exploration",
  "wave": 3,
  "infectedPlayers": ["player_2", "player_3", "player_4"],
  "humanPlayers": ["player_1"],
  "taskProgress": 8,
  "nearestHuman": "player_1",
  "botRoom": "Exit Gate"
}
```

### Agent Decision
The **BehaviorDirector** applies the final rule:
```
humanPlayers.length == 1 → final_hunt
shouldChase = True
```

This condition is checked first, before all others.

### Output Action
```json
{
  "botId": "player_2",
  "behaviorMode": "final_hunt",
  "targetRoom": null,
  "targetPlayer": null,
  "shouldChase": true,
  "trace": "Mode: final_hunt chosen by rule engine."
}
```
The demo also adds an explicit trace entry:
```
"trace": "3 infected vs 1 human. Full horror survival mode."
```

### Why It Matters in Gameplay
`final_hunt` is the climax state of THE INFECTED. It signals to Unity:
- All infected bots converge on the last human
- Maximum horror intensity — jump scare triggers, music shift
- Human must complete remaining tasks or reach exit before being caught

This mode is intentionally triggered by a simple, unmistakable condition (`len(humanPlayers) == 1`). Simplicity here is a feature: the backend can reliably detect this state from any Unity payload and respond consistently. The escalation from `stealth_fake_task` → `stalk` → `aggressive_chase` → `final_hunt` across a match lifecycle creates a satisfying, AI-driven horror arc without any scripted event triggers.

---

## Summary: Trace Card Reference

| Card Type | Triggered By | Agent | Key Output |
|---|---|---|---|
| `register_bot` | Match start | StateAgent + BehaviorDirector | personality, initial mode |
| `decide_action_early` | Wave ≤ 1, low infected | BehaviorDirector | `stealth_fake_task`, targetRoom |
| `respond` | Emergency meeting chat | ChatAgent + RefereeAgent | messages[], safety-filtered |
| `vote` | Meeting vote phase | VoteAgent | voteTarget (strategic) |
| `decide_action_late` | Infected ≥ humans | BehaviorDirector | `aggressive_chase`, shouldChase=true |
| `final_hunt` | 1 human remains | BehaviorDirector | `final_hunt`, shouldChase=true |
