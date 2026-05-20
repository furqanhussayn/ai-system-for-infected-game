$ErrorActionPreference = 'Stop'

$BaseUrl = $env:BASE_URL
if (-not $BaseUrl) {
    $BaseUrl = 'http://127.0.0.1:8000'
}

function Invoke-JsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('Get', 'Post')]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "$BaseUrl$Path"
    if ($Method -eq 'Get') {
        return Invoke-RestMethod -Uri $uri -Method Get
    }

    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 20
        return Invoke-RestMethod -Uri $uri -Method Post -ContentType 'application/json' -Body $json
    }

    return Invoke-RestMethod -Uri $uri -Method Post
}

function Assert-AllowedFieldSet {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredFields,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    foreach ($field in $RequiredFields) {
        if (-not ($Object.PSObject.Properties.Name -contains $field)) {
            throw "$Label missing field: $field"
        }
    }
}

function Assert-NoLeaks {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $text = ($Object | ConvertTo-Json -Depth 20).ToLowerInvariant()
    foreach ($needle in @('chat lab', 'playground', 'backend', 'prompt', 'api', 'groq', 'gemini', 'openrouter')) {
        if ($text.Contains($needle)) {
            throw "$Label contains leak text: $needle"
        }
    }
}

Write-Output '== generalized smoke start =='

Write-Output '== register player_3 =='
$registerP3 = Invoke-JsonRequest -Method Post -Path '/register_bot' -Body @{
    matchId = 'GEN_SMOKE_P3'
    botId = 'player_3'
    botName = 'Player 3'
    wave = 1
    cycle = 1
    phase = 'GasWave'
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    humanPlayers = @('player_1', 'player_2', 'player_4')
    infectedPlayers = @('player_3')
    taskProgress = 2
}
$registerP3 | ConvertTo-Json -Depth 20
if ($registerP3.botId -ne 'player_3') { throw 'register player_3 returned wrong botId' }
if (-not @('quiet','deflector','framer','panicker','crowd_follower').Contains($registerP3.personality)) { throw 'register player_3 returned invalid personality' }
if (-not @('stealth_fake_task','stalk','aggressive_chase','final_hunt','frozen','idle').Contains($registerP3.behaviorMode)) { throw 'register player_3 returned invalid behaviorMode' }

Write-Output '== decide player_3 =='
$decideP3 = Invoke-JsonRequest -Method Post -Path '/decide_action' -Body @{
    matchId = 'GEN_SMOKE_P3'
    phase = 'ExplorationB'
    wave = 2
    cycle = 2
    botId = 'player_3'
    botName = 'Player 3'
    infectedPlayers = @('player_3')
    humanPlayers = @('player_1', 'player_2', 'player_4')
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    taskProgress = 4
    nearestHuman = 'player_1'
    botRoom = 'Electrical'
    nearestHumanRoom = 'CentralHub'
    secondsSinceLastSeenHuman = 3.4
    isFinalChase = $false
}
$decideP3 | ConvertTo-Json -Depth 20
if ($decideP3.botId -ne 'player_3') { throw 'decide player_3 returned wrong botId' }
if ($decideP3.targetPlayer -eq 'player_3') { throw 'decide player_3 targeted itself' }
if ($null -ne $decideP3.targetPlayer -and @('player_1', 'player_2', 'player_4') -notcontains $decideP3.targetPlayer) { throw 'decide player_3 targeted invalid human' }
if (-not @('stealth_fake_task','stalk','aggressive_chase','final_hunt','frozen','idle').Contains($decideP3.behaviorMode)) { throw 'decide player_3 returned invalid behaviorMode' }

Write-Output '== respond player_4 =='
$respondP4 = Invoke-JsonRequest -Method Post -Path '/respond' -Body @{
    matchId = 'GEN_SMOKE_P4'
    phase = 'Meeting'
    wave = 2
    cycle = 2
    botId = 'player_4'
    botName = 'Player 4'
    personality = 'quiet'
    message = 'player 4 is sus'
    latestMessage = @{
        sender = 'player_1'
        senderName = 'Player 1'
        text = 'player 4 is sus'
    }
    recentChat = @(
        @{
            sender = 'player_1'
            senderName = 'Player 1'
            text = 'player 4 is sus'
        }
    )
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    humanPlayers = @('player_1', 'player_2', 'player_3')
    infectedPlayers = @('player_4')
}
$respondP4 | ConvertTo-Json -Depth 20
Assert-AllowedFieldSet -Object $respondP4 -RequiredFields @('botId', 'respond', 'messages', 'typingDelaySeconds', 'secondMessageDelaySeconds', 'trace') -Label 'respond player_4'
Assert-NoLeaks -Object $respondP4 -Label 'respond player_4'
if ($respondP4.botId -ne 'player_4') { throw 'respond player_4 returned wrong botId' }

Write-Output '== vote player_4 =='
$voteP4 = Invoke-JsonRequest -Method Post -Path '/vote' -Body @{
    matchId = 'GEN_SMOKE_P4'
    phase = 'AntidoteVote'
    wave = 2
    cycle = 2
    botId = 'player_4'
    botName = 'Player 4'
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    humanPlayers = @('player_1', 'player_2', 'player_3')
    infectedPlayers = @('player_4')
    recentChat = @(
        @{
            sender = 'player_1'
            senderName = 'Player 1'
            text = 'player 4 is sus'
        }
    )
}
$voteP4 | ConvertTo-Json -Depth 20
Assert-AllowedFieldSet -Object $voteP4 -RequiredFields @('botId', 'voteTarget', 'reason', 'trace') -Label 'vote player_4'
if ($voteP4.botId -ne 'player_4') { throw 'vote player_4 returned wrong botId' }
if ($voteP4.voteTarget -eq 'player_4') { throw 'vote player_4 voted self' }
if ($voteP4.voteTarget -eq 'player_4') { throw 'vote player_4 voted infected teammate' }
if (@('player_1', 'player_2', 'player_3') -notcontains $voteP4.voteTarget) { throw 'vote player_4 did not choose a human target' }

Write-Output '== multiple infected bots =='
$voteP2 = Invoke-JsonRequest -Method Post -Path '/vote' -Body @{
    matchId = 'GEN_SMOKE_MULTI'
    phase = 'AntidoteVote'
    wave = 3
    cycle = 1
    botId = 'player_2'
    botName = 'Player 2'
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    humanPlayers = @('player_1', 'player_3')
    infectedPlayers = @('player_2', 'player_4')
    recentChat = @(
        @{
            sender = 'player_1'
            senderName = 'Player 1'
            text = 'player 2 is sus'
        }
    )
}
$voteP4Multi = Invoke-JsonRequest -Method Post -Path '/vote' -Body @{
    matchId = 'GEN_SMOKE_MULTI'
    phase = 'AntidoteVote'
    wave = 3
    cycle = 1
    botId = 'player_4'
    botName = 'Player 4'
    alivePlayers = @('player_1', 'player_2', 'player_3', 'player_4')
    humanPlayers = @('player_1', 'player_3')
    infectedPlayers = @('player_2', 'player_4')
    recentChat = @(
        @{
            sender = 'player_1'
            senderName = 'Player 1'
            text = 'player 4 is sus'
        }
    )
}
$voteP2 | ConvertTo-Json -Depth 20
$voteP4Multi | ConvertTo-Json -Depth 20
if ($voteP2.voteTarget -in @('player_2', 'player_4')) { throw 'player_2 voted an infected teammate' }
if ($voteP4Multi.voteTarget -in @('player_2', 'player_4')) { throw 'player_4 voted an infected teammate' }
if (@('player_1', 'player_3') -notcontains $voteP2.voteTarget) { throw 'player_2 vote target was not a human' }
if (@('player_1', 'player_3') -notcontains $voteP4Multi.voteTarget) { throw 'player_4 vote target was not a human' }

Write-Output '== generalized smoke complete =='
