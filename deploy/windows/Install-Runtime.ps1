[CmdletBinding()]
param([switch]$Apply)
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
if (-not (Test-Path $PythonExe)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $Installer = Join-Path $RuntimeRoot 'python-installer.exe'
    Invoke-WebRequest -UseBasicParsing -Uri $Manifest.installerUrl -OutFile $Installer
    if ((Get-FileHash $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Manifest.installerSha256) {
        throw 'Python installer does not match the SHA-256 published by python.org. Nothing executed.'
    }
    $Signature = Get-AuthenticodeSignature -FilePath $Installer
    if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Subject -notlike ('*' + $Manifest.signatureSubjectMustContain + '*')) {
        throw 'Python installer signature validation failed. Nothing executed.'
    }
    $Arguments = @('/quiet', 'InstallAllUsers=0', 'Include_launcher=0', 'Include_test=0', 'PrependPath=0', ('TargetDir="' + $PythonRoot + '"'))
    $Process = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru
    if ($Process.ExitCode -notin @(0, 3010)) { throw 'Python installation failed.' }
}
$Version = & $PythonExe -c 'import platform,struct; print(platform.python_version()); assert struct.calcsize("P") == 8'
if ($LASTEXITCODE -ne 0 -or $Version -ne $Manifest.pythonVersion) { throw 'Unexpected Python runtime version or architecture.' }
$Venv = Join-Path $RuntimeRoot 'venv'
& $PythonExe -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
& $VenvPython -m pip install --only-binary=:all: -r (Join-Path $RepoRoot 'live\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed.' }
& $VenvPython -m unittest discover -s (Join-Path $RepoRoot 'live\tests') -q
if ($LASTEXITCODE -ne 0) { throw 'Synthetic safety tests failed. Observer remains inactive.' }
Write-Output 'Runtime installed and synthetic tests passed. No observer/task/trading was started.'
