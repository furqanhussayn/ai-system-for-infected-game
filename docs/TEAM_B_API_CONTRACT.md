Team B API Contract
Base URL example: http://localhost:8000

Overview
This file documents the Team A backend endpoints Team B (Unity) will call. All example JSON payloads are exact shapes expected by the backend scaffold (zero-cost rule-based behavior). Use ngrok or localhost in development.

Endpoints

1) GET /health
- Purpose: simple liveness check and service identity.
- Unity call timing: on game client startup or when validating backend availability.
- Request: none
- Response (200):
{
  "status": "ok",
  "service": "infected-ai-backend"
}
- Notes: Retry on network errors; treat non-200 as backend unavailable.

2) POST /register_bot
- Purpose: register a newly infected bot with Team A and receive assigned personality and initial behavior mode.
- Unity call timing: when a player becomes infected and Unity hands control to the AI backend (immediately after infection takeover).
- Request JSON (exact):
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "wave": 1,
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"]
}
- Response JSON (example):
{
  "botId": "player_2",
  "personality": "deflector",
  "behaviorMode": "stealth_fake_task",
  "trace": "Registered bot with personality deflector and early stealth behavior."
}
- What Unity should do with the response:
  - Save `personality` and `behaviorMode` in the local bot controller state.
  - Use `behaviorMode` to select initial movement/AI drive (fake tasks, wandering, etc.).
  - Send trace to in-game debug overlay (optional).
- Error handling:
  - 4xx/5xx: retry up to 2 times with short backoff; if still failing, default to local rule: assign `stealth_fake_task` and continue (log failure).

3) POST /decide_action
- Purpose: ask Team A which high-level action the bot should take next.
- Unity call timing: at behavior updates (every 20–30s recommended) and on important events (meeting start, voting start, wave infection, final hunt trigger).
- Request JSON (exact):
{
  "matchId": "ROOM123",
  "phase": "exploration",
  "wave": 2,
  "botId": "player_2",
  "infectedPlayers": ["player_2"],
  "humanPlayers": ["player_1","player_3","player_4"],
  "taskProgress": 3,
  "nearestHuman": "player_3",
  "botRoom": "Electrical"
}
- Response JSON (example):
{
  "botId": "player_2",
  "behaviorMode": "stealth_fake_task",
  "targetRoom": "Electrical",
  "targetPlayer": null,
  "shouldChase": false,
  "trace": "Early wave. Bot should fake tasks and avoid obvious aggression."
}
- What Unity should do with the response:
  - Update bot state `behaviorMode` and choose movement target: `targetRoom` or `targetPlayer`.
  - If `shouldChase` true, switch to chase AI; else use fake-task or stalking movement.
  - Send trace to debug overlay.
- Error handling:
  - If request fails, fall back to local rule: when wave <=1 use `stealth_fake_task`, when infected>=humans use `aggressive_chase`, otherwise `stalk`.

4) POST /respond
- Purpose: generate chat messages for the bot during meetings.
- Unity call timing: when a meeting chat should include bot responses (meeting start or when new chat message mentions bot).
- Request JSON (exact):
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "message": "player 2 is sus",
  "recentChat": [ {"sender":"player_1","text":"player 2 is sus"} ],
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"]
}
- Response JSON (example):
{
  "botId": "player_2",
  "messages": ["bro what??","i was literally doing wires"],
  "trace": "Bot was directly accused, so it denied and defended itself."
}
- What Unity should do with the response:
  - Enqueue `messages` to the meeting chat UI with timing rules (split messages: show first instantly, second after 1.5–3s per PRD).
  - Apply typing indicator delays to feel human.
  - Respect message splitting and avoid sending additional AI calls for the same chat event.
- Error handling:
  - If call fails, Unity may use canned local messages per personality (e.g., "hmm", "idk") and log the failure.

5) POST /vote
- Purpose: ask the bot whom to vote for during voting phase.
- Unity call timing: once when voting phase starts for each bot.
- Request JSON (exact):
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"],
  "recentChat": [ {"sender":"player_1","text":"player 2 is sus"}, {"sender":"player_3","text":"yeah player 2 weird"} ]
}
- Response JSON (example):
{
  "botId": "player_2",
  "voteTarget": "player_1",
  "trace": "Player 1 accused the bot, so bot voted against them."
}
- What Unity should do with the response:
  - Apply the `voteTarget` in the voting UI and send the vote to Firebase as the player's vote.
  - Show trace in debug overlay if available.
- Error handling:
  - If call fails, choose a random alive non-self human and continue; log the failure.

6) GET /trace/{matchId}
- Purpose: retrieve all stored traces for a match for the debug/trace overlay (judging/demo tool).
- Unity call timing: when opening the debug trace overlay or periodically when debugging the match.
- Request example: GET /trace/ROOM123
- Response JSON (example):
{
  "traces": [ { /* trace objects written by backend */ } ]
}
- What Unity should do with the response:
  - Render the list in the Antigravity Agent Trace overlay.
  - No gameplay effect.
- Error handling: show "no traces available" and allow retry.

No-cost AI call rules (must be enforced by Unity and the backend)
- Only call /respond when a meeting chat mentions or directly accuses a bot, or at meeting start if Unity wants bot responses.
- Only call /decide_action on important events (behavior update every 20–30s, meeting start, voting start, wave infection, final hunt). Avoid calling per-frame.
- Only call /vote once per voting phase per bot.
- Retry policy: small backoff for transient network errors; don't retry in tight loops to avoid accidental cost.

Notes and integration tips
- Keep a client-side cache of last decision/behaviorMode to avoid unnecessary decide_action calls.
- Provide a local fallback (simple heuristics) so gameplay remains uninterrupted if backend is unreachable.
- Use matchId to scope traces and bot state.
- For development, set `AI_MODE=rules` to avoid remote LLM usage.

Examples
- Base URL in Unity: "http://localhost:8000" or an ngrok URL when exposing locally.

End of contract.
