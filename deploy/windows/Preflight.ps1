[CmdletBinding()]
param([string]$PythonExe = (Join-Path $env:LOCALAPPDATA 'VORTEX\runtime\venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path $PythonExe)) { throw 'Pinned Python runtime is not installed. Preflight made no changes.' }
foreach ($Name in @('VORTEX_EXPECTED_LOGIN', 'VORTEX_SESSION_UTC_OFFSET_MINUTES', 'VORTEX_STATE_DIR')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) { throw ('Required private setting is missing: ' + $Name) }
}
$StatePath = [IO.Path]::GetFullPath($env:VORTEX_STATE_DIR)
if ($StatePath.StartsWith($RepoRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or $StatePath -eq $RepoRoot) {
    throw 'Runtime state must be outside the repository.'
}
& $PythonExe -c 'import MetaTrader5,pandas,numpy; assert MetaTrader5.__version__ == "5.0.6180"; assert pandas.__version__ == "2.2.3"; assert numpy.__version__ == "2.3.5"; print("Pinned imports OK; no terminal connection attempted.")'
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency preflight failed.' }
& $PythonExe (Join-Path $RepoRoot 'live\observe_v02.py') --check
if ($LASTEXITCODE -ne 0) { throw 'Read-only v0.2 configuration preflight failed.' }
& $PythonExe -m unittest discover -s (Join-Path $RepoRoot 'live\tests') -q
if ($LASTEXITCODE -ne 0) { throw 'Safety tests failed.' }
Write-Output 'Preflight passed. No MT5 initialize, data collection, broker call or process activation performed.'
