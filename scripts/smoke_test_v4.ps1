$B = $env:BASE_URL
if (-not $B) { $B = 'http://127.0.0.1:8000' }
Write-Output '== /health =='
try { Invoke-RestMethod -Uri "$B/health" -Method Get | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /register_bot =='
$reg = '{
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
try { Invoke-RestMethod -Uri "$B/register_bot" -Method Post -Body $reg -ContentType 'application/json' | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /decide_action =='
$dec = '{
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
try { Invoke-RestMethod -Uri "$B/decide_action" -Method Post -Body $dec -ContentType 'application/json' | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /respond =='
$resp = '{
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
try { Invoke-RestMethod -Uri "$B/respond" -Method Post -Body $resp -ContentType 'application/json' | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /vote =='
$vote = '{
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
try { Invoke-RestMethod -Uri "$B/vote" -Method Post -Body $vote -ContentType 'application/json' | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /unregister_bot =='
$un = '{
  "matchId": "ROOM123",
  "botId": "player_2",
  "reason": "antidote_cure"
}'
try { Invoke-RestMethod -Uri "$B/unregister_bot" -Method Post -Body $un -ContentType 'application/json' | ConvertTo-Json -Depth 10 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }

Write-Output '== /trace/ROOM123 =='
try { Invoke-RestMethod -Uri "$B/trace/ROOM123" -Method Get | ConvertTo-Json -Depth 20 } catch { Write-Output 'ERROR:'; Write-Output $_.Exception.Message }
