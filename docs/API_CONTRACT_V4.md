# Team A API Contract V4

Base URL: `http://127.0.0.1:8000`

Official endpoints:

- `GET /health`
- `POST /register_bot`
- `POST /unregister_bot`
- `POST /decide_action`
- `POST /respond`
- `POST /vote`
- `GET /trace/{matchId}`

Optional endpoints that may remain available:

- `GET /`
- `GET /trace_viewer/{matchId}`
- `GET /trace_debug/{matchId}`
- `GET /chat_lab`
- `GET /llm/status`
- demo endpoints under `/demo`

## Required enums and IDs

Player IDs:

- `player_1`
- `player_2`
- `player_3`
- `player_4`

Display names:

- `Player 1`
- `Player 2`
- `Player 3`
- `Player 4`

Phase strings:

- `Lobby`
- `ExplorationA`
- `GasWave`
- `ExplorationB`
- `Meeting`
- `AntidoteVote`
- `AntidoteFreeze`
- `FinalChase`
- `Ended`

Behavior modes:

- `stealth_fake_task`
- `stalk`
- `aggressive_chase`
- `final_hunt`
- `frozen`
- `idle`

Personalities:

- `quiet`
- `deflector`
- `framer`
- `panicker`
- `crowd_follower`

## GET /health

Response:

```json
{
  "status": "ok",
  "service": "infected-ai-backend",
  "contractVersion": "v4",
  "aiMode": "rules",
  "llmProvider": "groq",
  "firebaseConfigured": true
}
```

Notes:

- `aiMode` comes from `AI_MODE`, default `rules`.
- `llmProvider` comes from `LLM_PROVIDER`, default `groq`.
- `firebaseConfigured` is `true` when Firebase config such as `FIREBASE_DATABASE_URL` is present.
- No API keys are ever returned.

## POST /register_bot

Request example:

```json
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "botName": "Player 2",
  "wave": 1,
  "cycle": 1,
  "phase": "GasWave",
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "humanPlayers": ["player_1", "player_3", "player_4"],
  "infectedPlayers": ["player_2"],
  "taskProgress": 2
}
```

Response:

```json
{
  "ok": true,
  "botId": "player_2",
  "personality": "deflector",
  "behaviorMode": "stealth_fake_task",
  "trace": "Registered bot with personality deflector and early stealth behavior."
}
```

Notes:

- Bot state is stored by `matchId` and `botId`.
- Re-registering the same bot is safe and idempotent.
- A trace entry is recorded.

## POST /unregister_bot

Request example:

```json
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "reason": "antidote_cure"
}
```

Response:

```json
{
  "ok": true,
  "botId": "player_2",
  "trace": "Bot player_2 unregistered after antidote_cure."
}
```

Notes:

- The endpoint is idempotent.
- If the bot does not exist, it still returns `ok: true`.
- A trace entry is recorded either way.

## POST /decide_action

Request example:

```json
{
  "matchId": "ROOM123",
  "phase": "ExplorationB",
  "wave": 2,
  "cycle": 2,
  "botId": "player_2",
  "botName": "Player 2",
  "infectedPlayers": ["player_2"],
  "humanPlayers": ["player_1", "player_3", "player_4"],
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "taskProgress": 3,
  "nearestHuman": "player_3",
  "botRoom": "Electrical",
  "nearestHumanRoom": "CentralHub",
  "secondsSinceLastSeenHuman": 4.2,
  "isFinalChase": false
}
```

Response:

```json
{
  "botId": "player_2",
  "behaviorMode": "stalk",
  "targetRoom": "CentralHub",
  "targetPlayer": "player_3",
  "shouldChase": false,
  "nextDecisionInSeconds": 24,
  "trace": "Mid game: stalk nearest human but avoid obvious chase."
}
```

Rules:

- `nextDecisionInSeconds` always stays between 20 and 30.
- If `isFinalChase` is `true` or only one human remains, return `final_hunt` and `shouldChase: true`.
- If infected are fewer than humans, prefer `stealth_fake_task`, sometimes `stalk`.
- If infected are at least humans, prefer `aggressive_chase`.
- This endpoint returns intent only and never sleeps.

## POST /respond

Request example:

```json
{
  "matchId": "ROOM123",
  "phase": "Meeting",
  "wave": 2,
  "cycle": 2,
  "botId": "player_2",
  "botName": "Player 2",
  "personality": "deflector",
  "message": "player 2 is sus",
  "latestMessage": {
    "sender": "player_1",
    "senderName": "Player 1",
    "text": "player 2 is sus"
  },
  "recentChat": [
    {"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"}
  ],
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "humanPlayers": ["player_1", "player_3", "player_4"],
  "infectedPlayers": ["player_2"]
}
```

Response when speaking:

```json
{
  "botId": "player_2",
  "respond": true,
  "messages": ["bro what??", "i was literally doing wires"],
  "typingDelaySeconds": 2.6,
  "secondMessageDelaySeconds": 1.8,
  "trace": "Bot was directly accused, so it denied and defended itself."
}
```

Response when silent:

```json
{
  "botId": "player_2",
  "respond": false,
  "messages": [],
  "typingDelaySeconds": 0,
  "secondMessageDelaySeconds": 0,
  "trace": "Bot stayed silent because it was not mentioned."
}
```

Rules:

- Production responses return immediately.
- Unity waits using the returned delay values.
- Messages are 1-2 short casual chat lines.
- Never reveal hidden role or internal AI/provider/backend terms.

## POST /vote

Request example:

```json
{
  "matchId": "ROOM123",
  "phase": "AntidoteVote",
  "wave": 2,
  "cycle": 2,
  "botId": "player_2",
  "botName": "Player 2",
  "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
  "humanPlayers": ["player_1", "player_3", "player_4"],
  "infectedPlayers": ["player_2"],
  "recentChat": [
    {"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"},
    {"sender": "player_3", "senderName": "Player 3", "text": "yeah player 2 weird"}
  ]
}
```

Response:

```json
{
  "botId": "player_2",
  "voteTarget": "player_1",
  "reason": "player_1 accused the bot first.",
  "trace": "player_1 accused the bot first."
}
```

Rules:

- Prefer humans.
- Never intentionally vote an infected bot when humans exist.
- If accused by a human, vote the accusing human first.
- If no accuser exists, choose a random human.
- If no valid human exists, `voteTarget` can be `null`.

## GET /trace/{matchId}

Response example:

```json
{
  "matchId": "ROOM123",
  "count": 2,
  "traces": [
    {
      "ts": "2026-05-19T12:00:00Z",
      "eventType": "respond",
      "action": "respond",
      "matchId": "ROOM123",
      "botId": "player_2",
      "input": "{...}",
      "output": "{...}",
      "trace": "Bot denied accusation."
    }
  ]
}
```

Notes:

- Trace records include register, unregister, decide_action, respond, and vote.
- The trace viewer can remain available separately.

## Fallback behavior

- `AI_MODE=rules` must work fully offline.
- `AI_MODE=groq` can call Groq when a key exists, otherwise it falls back to rules.
- Unsupported or unavailable provider modes should also fall back to rules.
- No production response should sleep to simulate typing.

## Unity timing contract

- The API returns `typingDelaySeconds` and `secondMessageDelaySeconds`.
- Unity is responsible for waiting before showing the message bubbles.
- The backend must not block the HTTP response for typing effects.