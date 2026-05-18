SAMPLE PAYLOADS

Base URL: http://localhost:8000

1) Register Bot
POST /register_bot

Request:
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "wave": 1,
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"]
}

Response:
{
  "botId": "player_2",
  "personality": "deflector",
  "behaviorMode": "stealth_fake_task",
  "trace": "Registered bot with personality deflector and early stealth behavior."
}

2) Decide Action
POST /decide_action

Request:
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

Response:
{
  "botId": "player_2",
  "behaviorMode": "stalk",
  "targetRoom": "Electrical",
  "targetPlayer": null,
  "shouldChase": false,
  "trace": "Mid game: bot should stalk nearby humans."
}

3) Respond
POST /respond

Request:
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "message": "player 2 is sus",
  "recentChat": [ {"sender":"player_1","text":"player 2 is sus"} ],
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"]
}

Response:
{
  "botId": "player_2",
  "messages": ["bro what??","i was literally doing wires"],
  "trace": "Bot was directly accused, so it denied and defended itself."
}

4) Vote
POST /vote

Request:
{
  "matchId": "ROOM123",
  "botId": "player_2",
  "alivePlayers": ["player_1","player_2","player_3","player_4"],
  "infectedPlayers": ["player_2"],
  "recentChat": [ {"sender":"player_1","text":"player 2 is sus"} ]
}

Response:
{
  "botId": "player_2",
  "voteTarget": "player_1",
  "trace": "Player 1 accused the bot, so bot voted against them."
}

5) Trace
GET /trace/ROOM123

Response:
{
  "traces": [ { /* trace objects stored by backend */ } ]
}

Notes: paste these exactly into Swagger UI or use curl to test endpoints locally.
