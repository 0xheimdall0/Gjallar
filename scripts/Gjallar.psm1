<#
.SYNOPSIS
    Gjallar client for PowerShell.

.DESCRIPTION
    Import once, then report from any script on the machine:

        Import-Module "$HOME\Gjallar\scripts\Gjallar.psm1"

        Send-GjallarEvent -Title "Backup finished" -Message "412 GB" -Severity info -Tags backup
        Send-GjallarPing  -Name  nightly-backup -Every 86400 -Grace 3600

    Configuration comes from two environment variables, set once for your user:

        [Environment]::SetEnvironmentVariable('GJALLAR_URL',   'https://gjallar.example.com', 'User')
        [Environment]::SetEnvironmentVariable('GJALLAR_TOKEN', 'sig_your_source_token',       'User')

    Neither function throws. If Gjallar is unreachable they warn and return, so
    reporting can never break the script doing the reporting.
#>

function Get-GjallarConfig {
    $url = if ($env:GJALLAR_URL) { $env:GJALLAR_URL } else { 'http://127.0.0.1:8000' }
    $token = $env:GJALLAR_TOKEN

    if (-not $token) {
        Write-Warning 'GJALLAR_TOKEN is not set; nothing will be reported.'
        return $null
    }

    [pscustomobject]@{ Url = $url; Headers = @{ Authorization = "Bearer $token" } }
}

function Send-GjallarEvent {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Title,
        [string] $Message,
        [ValidateSet('debug', 'info', 'warn', 'error', 'critical')]
        [string] $Severity = 'info',
        [string[]] $Tags = @(),
        [hashtable] $Metadata,
        [string] $Link
    )

    $config = Get-GjallarConfig
    if (-not $config) { return }

    $body = @{ title = $Title; severity = $Severity; tags = $Tags }
    if ($Message)  { $body.message = $Message }
    if ($Metadata) { $body.metadata = $Metadata }
    if ($Link)     { $body.link = $Link }

    try {
        Invoke-RestMethod -Method Post -Uri "$($config.Url)/api/events" `
            -Headers $config.Headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ($body | ConvertTo-Json -Depth 5 -Compress) | Out-Null
    }
    catch {
        Write-Warning "Gjallar: could not file event - $($_.Exception.Message)"
    }
}

function Send-GjallarPing {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $Name,

        # Required on the very first ping — it is what registers the heartbeat.
        # Optional afterwards; supplying it again changes the schedule.
        [int] $Every,
        [int] $Grace
    )

    $config = Get-GjallarConfig
    if (-not $config) { return }

    $body = @{}
    if ($Every) { $body.expected_interval_seconds = $Every }
    if ($Grace) { $body.grace_seconds = $Grace }

    try {
        Invoke-RestMethod -Method Post -Uri "$($config.Url)/api/heartbeats/$Name/ping" `
            -Headers $config.Headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ($body | ConvertTo-Json -Compress) | Out-Null
    }
    catch {
        Write-Warning "Gjallar: could not ping heartbeat - $($_.Exception.Message)"
    }
}

Export-ModuleMember -Function Send-GjallarEvent, Send-GjallarPing
