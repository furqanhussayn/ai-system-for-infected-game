$ErrorActionPreference = 'Stop'
$baseUrl = 'http://127.0.0.1:8000'
$matchId = 'ROOM123'

Write-Host '=== /llm/status ==='
$status = Invoke-RestMethod -Method Get -Uri "$baseUrl/llm/status"
$status | ConvertTo-Json -Depth 6

Write-Host '=== /llm/ping ==='
$ping = Invoke-RestMethod -Method Get -Uri "$baseUrl/llm/ping"
$ping | ConvertTo-Json -Depth 6

Write-Host '=== /respond ==='
$body = @{
    matchId = $matchId
    phase = 'Meeting'
    wave = 2
    cycle = 1
    botId = 'player_2'
    botName = 'Player 2'
    personality = 'deflector'
    message = 'player 2 is sus'
    latestMessage = @{ sender = 'player_1'; senderName = 'Player 1'; text = 'player 2 is sus' }
    recentChat = @(@{ sender = 'player_1'; senderName = 'Player 1'; text = 'player 2 is sus' })
    alivePlayers = @('player_1','player_2','player_3','player_4')
    humanPlayers = @('player_1','player_3','player_4')
    infectedPlayers = @('player_2')
} | ConvertTo-Json -Depth 10
$respond = Invoke-RestMethod -Method Post -Uri "$baseUrl/respond" -ContentType 'application/json' -Body $body
$respond | ConvertTo-Json -Depth 10

Write-Host '=== /trace/ROOM123 ==='
$trace = Invoke-RestMethod -Method Get -Uri "$baseUrl/trace/$matchId"
$trace | ConvertTo-Json -Depth 10

$latest = if ($trace.traces -and $trace.traces.Count -gt 0) { $trace.traces[-1] } else { $null }
if ($latest) {
    Write-Host '=== latest trace summary ==='
    Write-Host ("llm_used=" + ($latest.trace -match 'llm_used=True'))
    Write-Host ("fallback_reason=" + (($latest.trace -split '\|') | Where-Object { $_ -match 'fallback_reason=' } | Select-Object -Last 1))
}
