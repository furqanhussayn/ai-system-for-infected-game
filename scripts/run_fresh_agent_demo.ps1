$ErrorActionPreference = 'Stop'
$baseUrl = 'http://127.0.0.1:8000'
$matchId = 'AGENT_ROOM'

Write-Host 'Refreshing agent demo...'
$null = Invoke-WebRequest -Method Post -Uri "$baseUrl/demo/agent_quick/$matchId" -MaximumRedirection 0 -UseBasicParsing -ErrorAction SilentlyContinue

Write-Host 'Trace viewer URL:'
Write-Host "$baseUrl/trace_viewer/$matchId?fresh=$(Get-Date -AsUTC -Format o)"

$trace = Invoke-RestMethod -Method Get -Uri "$baseUrl/trace/$matchId"
$latest = if ($trace.traces -and $trace.traces.Count -gt 0) { $trace.traces[-1] } else { $null }

Write-Host 'Latest trace summary:'
if ($latest) {
    Write-Host ($latest.action + ' | ' + $latest.source)
    Write-Host ('trace=' + $latest.trace)
} else {
    Write-Host 'No trace entries found.'
}
