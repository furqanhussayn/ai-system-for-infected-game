#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}

curl -sS "$BASE_URL/health"

curl -sS -X POST "$BASE_URL/register_bot" \
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

curl -sS -X POST "$BASE_URL/decide_action" \
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

curl -sS -X POST "$BASE_URL/respond" \
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

curl -sS -X POST "$BASE_URL/vote" \
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

curl -sS -X POST "$BASE_URL/unregister_bot" \
  -H "Content-Type: application/json" \
  -d '{
    "matchId": "ROOM123",
    "botId": "player_2",
    "reason": "antidote_cure"
  }'

curl -sS "$BASE_URL/trace/ROOM123"