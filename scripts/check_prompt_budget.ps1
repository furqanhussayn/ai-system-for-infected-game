$ErrorActionPreference = 'Stop'
$baseUrl = 'http://127.0.0.1:8000'

function Show-Resp($body) {
    $r = Invoke-RestMethod -Method Post -Uri "$baseUrl/respond" -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 10)
    Write-Host '--- RESPOND ---'
    Write-Host ($r | ConvertTo-Json -Depth 6)
    if ($r.trace) { Write-Host 'trace:'; Write-Host $r.trace }
}

$direct = @{
    matchId = 'ROOM123'
    phase = 'Meeting'
    wave = 2
    cycle = 1
    botId = 'player_2'
    botName = 'Player 2'
    personality = 'deflector'
    message = 'player 2 is sus'
    latestMessage = @{ sender = 'player_1'; senderName = 'Player 1'; text = 'player 2 is sus' }
    recentChat = @(
        @{ sender = 'player_1'; senderName = 'Player 1'; text = 'player 2 is sus' },
        @{ sender = 'player_1'; senderName = 'Player 1'; text = 'i saw them near gen' },
        @{ sender = 'player_3'; senderName = 'Player 3'; text = 'nah i was doing wires' }
    )
    alivePlayers = @('player_1','player_2','player_3','player_4')
    humanPlayers = @('player_1','player_3','player_4')
    infectedPlayers = @('player_2')
}

$generic = @{
    matchId = 'ROOM123'
    phase = 'Meeting'
    wave = 1
    cycle = 1
    botId = 'player_2'
    botName = 'Player 2'
    personality = 'crowd_follower'
    message = 'hello cuties'
    latestMessage = @{ sender = 'player_1'; senderName = 'Player 1'; text = 'hello cuties' }
    recentChat = @(
        @{ sender = 'player_1'; senderName = 'Player 1'; text = 'hello cuties' }
    )
    alivePlayers = @('player_1','player_2','player_3','player_4')
    humanPlayers = @('player_1','player_3','player_4')
    infectedPlayers = @('player_2')
}

Show-Resp $direct
Show-Resp $generic
