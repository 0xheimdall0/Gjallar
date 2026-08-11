<#
.SYNOPSIS
    Reports disk space to Gjallar and pings the daily-health heartbeat.

.DESCRIPTION
    Run this from Task Scheduler once a day. It does two things:

      1. Files an event describing free space on every fixed drive, with a
         severity that escalates as space runs out.
      2. Pings a heartbeat, so that the machine going quiet is itself an alert.

    The second matters more than the first. A disk filling up is a slow problem
    you would probably notice; a laptop that stopped reporting for three days
    is the kind of thing that otherwise goes unnoticed.

.NOTES
    The token is read from the GJALLAR_TOKEN environment variable and is never
    stored in this file. Set it once, for your user only:

        [Environment]::SetEnvironmentVariable('GJALLAR_TOKEN', 'sig_...', 'User')

    Then open a new terminal so the variable is visible.
#>

[CmdletBinding()]
param(
    [string] $BaseUrl        = $(if ($env:GJALLAR_URL) { $env:GJALLAR_URL } else { 'http://127.0.0.1:8000' }),
    [string] $Token          = $env:GJALLAR_TOKEN,

    # Free space thresholds, in gigabytes.
    [int]    $WarnBelowGB    = 25,
    [int]    $ErrorBelowGB   = 10,

    [string] $HeartbeatName  = 'daily-health',
    # 26 hours: a daily job that runs a little late should not be an outage.
    [int]    $IntervalSeconds = 93600,
    [int]    $GraceSeconds    = 3600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Token) {
    Write-Error 'GJALLAR_TOKEN is not set. See the notes at the top of this script.'
    exit 1
}

$Headers = @{ Authorization = "Bearer $Token" }


function Send-GjallarEvent {
    param(
        [Parameter(Mandatory)] [string] $Title,
        [string] $Message,
        [ValidateSet('debug', 'info', 'warn', 'error', 'critical')]
        [string] $Severity = 'info',
        [string[]] $Tags = @(),
        [hashtable] $Metadata
    )

    $body = @{
        title    = $Title
        message  = $Message
        severity = $Severity
        tags     = $Tags
    }
    if ($Metadata) { $body.metadata = $Metadata }

    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/events" `
            -Headers $Headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ($body | ConvertTo-Json -Depth 5 -Compress) | Out-Null
    }
    catch {
        # Never let reporting failures break the thing being reported on.
        Write-Warning "Could not file event: $($_.Exception.Message)"
    }
}


function Send-GjallarPing {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [int] $Interval,
        [int] $Grace
    )

    $body = @{
        expected_interval_seconds = $Interval
        grace_seconds             = $Grace
    }

    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/heartbeats/$Name/ping" `
            -Headers $Headers `
            -ContentType 'application/json; charset=utf-8' `
            -Body ($body | ConvertTo-Json -Compress) | Out-Null
    }
    catch {
        Write-Warning "Could not ping heartbeat: $($_.Exception.Message)"
    }
}


# --- gather ------------------------------------------------------------------

$drives = Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType = 3'

$lines = @()
$metadata = @{}
$worstFreeGB = [double]::MaxValue

foreach ($drive in $drives) {
    $freeGB  = [math]::Round($drive.FreeSpace / 1GB, 1)
    $totalGB = [math]::Round($drive.Size / 1GB, 1)
    $percent = if ($totalGB -gt 0) { [math]::Round(100 * $freeGB / $totalGB, 1) } else { 0 }

    $lines += "{0} {1} GB free of {2} GB ({3}%)" -f $drive.DeviceID, $freeGB, $totalGB, $percent
    $metadata[$drive.DeviceID] = @{ free_gb = $freeGB; total_gb = $totalGB; percent_free = $percent }

    if ($freeGB -lt $worstFreeGB) { $worstFreeGB = $freeGB }
}

$severity =
    if     ($worstFreeGB -lt $ErrorBelowGB) { 'error' }
    elseif ($worstFreeGB -lt $WarnBelowGB)  { 'warn'  }
    else                                    { 'info'  }

$title = "Disk report: {0} GB free on the fullest drive" -f $worstFreeGB


# --- report ------------------------------------------------------------------

Send-GjallarEvent -Title $title `
                  -Message ($lines -join "`n") `
                  -Severity $severity `
                  -Tags @('disk', 'health') `
                  -Metadata $metadata

Send-GjallarPing -Name $HeartbeatName -Interval $IntervalSeconds -Grace $GraceSeconds

Write-Host "Reported: $title  [$severity]"
