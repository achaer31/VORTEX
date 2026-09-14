[CmdletBinding()]
param([switch]$StartObserver,
      [switch]$StartCollector,
      [string]$PythonExe = (Join-Path $env:LOCALAPPDATA 'VORTEX\runtime\venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($StartObserver -and $StartCollector) { throw 'Choose either collector or reviewed observer, not both.' }
$Mode = if ($StartCollector) { 'Collect' } else { 'Observe' }
if (-not $StartObserver -and -not $StartCollector) {
    & (Join-Path $PSScriptRoot 'Preflight.ps1') -PythonExe $PythonExe
    Write-Output 'DRY RUN: observer watchdog is inactive. No broker data collection started.'
    return
}
# A passed baseline is a separate reviewed result. This script never creates it.
if ($StartObserver -and $env:VORTEX_BASELINE_STATUS -ne 'passed_reviewed') {
    throw 'Baseline review gate not satisfied; observer remains inactive.'
}
& (Join-Path $PSScriptRoot 'Preflight.ps1') -PythonExe $PythonExe -Mode $Mode
New-Item -ItemType Directory -Force -Path $env:VORTEX_STATE_DIR | Out-Null
$StopFile = Join-Path $env:VORTEX_STATE_DIR 'STOP'
$LogFile = Join-Path $env:VORTEX_STATE_DIR 'observer-console.log'
$RunFlag = if ($StartCollector) { '--collect' } else { '--observe' }
while (-not (Test-Path $StopFile)) {
    & $PythonExe (Join-Path $RepoRoot 'live\observe_v02.py') $RunFlag 2>&1 | Out-File -Append -Encoding utf8 $LogFile
    $Code = $LASTEXITCODE
    # A guard halt or unexplained failure needs review, not an automatic retry.
    if ($Code -ne 0) { throw 'Observer halted; inspect private state and log. No automatic retry.' }
    if (Test-Path $StopFile) { break }
    Start-Sleep -Seconds 30
}
