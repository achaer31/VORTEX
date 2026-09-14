[CmdletBinding()]
param([switch]$Apply, [string]$OfflineBundlePath)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Manifest = Get-Content (Join-Path $PSScriptRoot 'runtime.json') -Raw | ConvertFrom-Json
$RuntimeRoot = Join-Path $env:LOCALAPPDATA 'VORTEX\runtime'
$PythonRoot = Join-Path $RuntimeRoot ('python-' + $Manifest.pythonVersion)
$PythonExe = Join-Path $PythonRoot 'python.exe'
if (-not $Apply) {
    Write-Output ('DRY RUN: official Python ' + $Manifest.pythonVersion + ' x64; valid PSF signature required.')
    Write-Output 'Would create isolated runtime outside repository and install live/requirements.txt.'
    Write-Output 'No download, install, terminal connection, task or trading activation performed.'
    return
}
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
if ($OfflineBundlePath) {
    $OfflineBundlePath = (Resolve-Path $OfflineBundlePath).Path
    $OfflineManifest = Get-Content (Join-Path $PSScriptRoot 'offline-runtime.json') -Raw | ConvertFrom-Json
    if ($OfflineManifest.pythonVersion -ne $Manifest.pythonVersion) { throw 'Offline runtime version mismatch.' }
    foreach ($Artifact in $OfflineManifest.files) {
        if ($Artifact.file -notmatch '^(python-installer\.exe|wheels/[A-Za-z0-9_.-]+\.whl)$') { throw 'Invalid offline artifact path.' }
        $ArtifactPath = Join-Path $OfflineBundlePath $Artifact.file
        if (-not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf) -or
            (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Artifact.sha256) {
            throw 'Offline artifact missing or checksum mismatch. Nothing executed.'
        }
    }
}
if (-not (Test-Path $PythonExe)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $Installer = Join-Path $RuntimeRoot 'python-installer.exe'
    if ($OfflineBundlePath) {
        Copy-Item -LiteralPath (Join-Path $OfflineBundlePath 'python-installer.exe') -Destination $Installer
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $Manifest.installerUrl -OutFile $Installer
    }
    if ((Get-FileHash $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Manifest.installerSha256) {
        throw 'Python installer does not match the SHA-256 published by python.org. Nothing executed.'
    }
    $Signature = Get-AuthenticodeSignature -FilePath $Installer
    if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Subject -notlike ('*' + $Manifest.signatureSubjectMustContain + '*')) {
        throw 'Python installer signature validation failed. Nothing executed.'
    }
    $InstallerLog = Join-Path $RuntimeRoot 'python-installer.log'
    $Arguments = @('/quiet', '/log', ('"' + $InstallerLog + '"'), 'InstallAllUsers=0', 'Include_launcher=0', 'Include_test=0', 'PrependPath=0', ('TargetDir="' + $PythonRoot + '"'))
    $Process = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru
    $Process.Refresh()
    if ($Process.ExitCode -eq 1625) { throw 'Python installation blocked by system policy (1625). Ask the server administrator/provider to permit the official installer; runtime remains inactive.' }
    if ($Process.ExitCode -notin @(0, 3010)) { throw ('Python installation failed; exit code ' + $Process.ExitCode + '. Inspect private python-installer.log.') }
}
# File-based probe avoids Windows PowerShell 5.1 native argument quote stripping.
$Probe = Join-Path $RuntimeRoot 'verify-python.py'
[IO.File]::WriteAllText($Probe, 'import platform,struct; print(platform.python_version()); assert struct.calcsize("P") == 8', (New-Object Text.UTF8Encoding($false)))
$Version = & $PythonExe $Probe
if ($LASTEXITCODE -ne 0 -or $Version -ne $Manifest.pythonVersion) { throw 'Unexpected Python runtime version or architecture.' }
$Venv = Join-Path $RuntimeRoot 'venv'
& $PythonExe -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if ($OfflineBundlePath) {
    & $VenvPython -m pip install --no-index --only-binary=:all: --find-links (Join-Path $OfflineBundlePath 'wheels') --require-hashes -r (Join-Path $PSScriptRoot 'offline-requirements.txt')
} else {
    & $VenvPython -m pip install --index-url 'https://pypi.org/simple' --only-binary=:all: -r (Join-Path $RepoRoot 'live\requirements.txt')
}
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed.' }
Push-Location $RepoRoot
try {
    & $VenvPython -m unittest discover -s (Join-Path $RepoRoot 'live\tests') -q
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic safety tests failed. Observer remains inactive.' }
} finally { Pop-Location }
Write-Output 'Runtime installed and synthetic tests passed. No observer/task/trading was started.'
