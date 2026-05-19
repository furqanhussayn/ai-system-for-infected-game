# Sample Payloads V4

Base URL used below:

```bash
http://127.0.0.1:8000
```

## GET /health

```bash
curl http://127.0.0.1:8000/health
```

## POST /register_bot

```bash
curl -X POST http://127.0.0.1:8000/register_bot \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## POST /unregister_bot

```bash
curl -X POST http://127.0.0.1:8000/unregister_bot \
  -H "Content-Type: application/json" \
  -d '{
    "matchId": "ROOM123",
    "botId": "player_2",
    "reason": "antidote_cure"
  }'
```

## POST /decide_action

```bash
curl -X POST http://127.0.0.1:8000/decide_action \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## POST /respond

```bash
curl -X POST http://127.0.0.1:8000/respond \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## POST /vote

```bash
curl -X POST http://127.0.0.1:8000/vote \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

## GET /trace/ROOM123

```bash
curl http://127.0.0.1:8000/trace/ROOM123
```