[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
if (-not $Apply) {
    Write-Output 'DRY RUN: would register VORTEX Demo Observer at user logon, interactive session, normal privileges.'
    Write-Output 'No task registered. Runtime, private environment and reviewed baseline are required first.'
    return
}
if ($env:VORTEX_BASELINE_STATUS -ne 'passed_reviewed') { throw 'Baseline review gate not satisfied.' }
& (Join-Path $PSScriptRoot 'Preflight.ps1')
$Script = Join-Path $PSScriptRoot 'Watch-Observer.ps1'
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -File "' + $Script + '" -StartObserver')
$User = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'VORTEX Demo Observer' -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings | Out-Null
Write-Output 'Observer task registered for next user logon; it was not started. It only runs observe mode.'
