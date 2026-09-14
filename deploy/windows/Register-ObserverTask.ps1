[CmdletBinding()]
param([switch]$Apply,
      [ValidateSet('Observe', 'Collect')][string]$Mode = 'Observe')
$ErrorActionPreference = 'Stop'
$TaskName = if ($Mode -eq 'Collect') { 'VORTEX Demo Collector' } else { 'VORTEX Demo Observer' }
if (-not $Apply) {
    Write-Output ('DRY RUN: would register ' + $TaskName + ' at user logon, interactive session, normal privileges.')
    Write-Output 'No task registered. Collection is read-only; reviewed observe still requires the passed baseline gate.'
    return
}
if ($Mode -eq 'Observe' -and $env:VORTEX_BASELINE_STATUS -ne 'passed_reviewed') { throw 'Baseline review gate not satisfied.' }
& (Join-Path $PSScriptRoot 'Preflight.ps1') -Mode $Mode
$Script = Join-Path $PSScriptRoot 'Watch-Observer.ps1'
$StartFlag = if ($Mode -eq 'Collect') { '-StartCollector' } else { '-StartObserver' }
$Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -File "' + $Script + '" ' + $StartFlag)
$User = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings | Out-Null
Write-Output ($TaskName + ' registered for next user logon; it was not started. Read-only, no execution enabled.')
