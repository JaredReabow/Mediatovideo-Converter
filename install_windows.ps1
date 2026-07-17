# Mediatovideo Converter Windows prerequisite installer and launcher.
# This script is called by run_windows.bat so every action remains visible.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:StepNumber = 0
$script:PythonExecutable = $null
$script:PythonPrefixArguments = @()

function Write-InstallerHeader {
    Clear-Host
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " Mediatovideo Converter - Windows startup" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "This window checks and installs the required components."
    Write-Host "It remains open so progress and errors are always visible."
    Write-Host ""
}

function Write-InstallerStep {
    param([Parameter(Mandatory = $true)][string]$Message)
    $script:StepNumber += 1
    Write-Host "[$($script:StepNumber)] $Message" -ForegroundColor Cyan
}

function Write-InstallerSuccess {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Stop-InstallerError {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][string]$Problem,
        [Parameter(Mandatory = $true)][string]$Action,
        [string]$Details = ""
    )
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host " STARTUP ERROR" -ForegroundColor Red
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host "Stage:   $Stage" -ForegroundColor Yellow
    Write-Host "Problem: $Problem" -ForegroundColor White
    if ($Details) {
        Write-Host "Details: $Details" -ForegroundColor DarkGray
    }
    Write-Host "What to do: $Action" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $extraPaths = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links",
        "$env:ProgramFiles\WinGet\Links"
    )
    $env:Path = (@($machinePath, $userPath) + $extraPaths | Where-Object { $_ }) -join ";"
}

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$PrefixArguments = @()
    )
    try {
        $command = Get-Command $Executable -ErrorAction Stop
        & $command.Source @PrefixArguments -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            $script:PythonExecutable = $command.Source
            $script:PythonPrefixArguments = $PrefixArguments
            return $true
        }
    }
    catch {
        return $false
    }
    return $false
}

function Find-CompatiblePython {
    $candidates = @(
        @{ Executable = "python"; Arguments = @() },
        @{ Executable = "python3"; Arguments = @() },
        @{ Executable = "py"; Arguments = @("-3.14") },
        @{ Executable = "py"; Arguments = @("-3") }
    )
    foreach ($candidate in $candidates) {
        if (Test-PythonCandidate -Executable $candidate.Executable -PrefixArguments $candidate.Arguments) {
            return $true
        }
    }
    return $false
}

function Require-WinGet {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-InstallerSuccess "Windows Package Manager (WinGet) is available."
        return
    }
    Stop-InstallerError `
        -Stage "Preparing automatic installation" `
        -Problem "Windows Package Manager (winget) is not available." `
        -Action "Install or update 'App Installer' from Microsoft Store, then run run_windows.bat again." `
        -Details "WinGet is included with supported Windows 10 and Windows 11 installations."
}

function Find-PythonManager {
    foreach ($name in @("pymanager", "py")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            & $command.Source help install *> $null
            if ($LASTEXITCODE -eq 0) {
                return $command.Source
            }
        }
    }
    $managerPaths = @(
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_3847v3x7pw1km\pymanager.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_qbz5n2kfra8p0\pymanager.exe"
    )
    foreach ($path in $managerPaths) {
        if (Test-Path $path) {
            & $path help install *> $null
            if ($LASTEXITCODE -eq 0) {
                return $path
            }
        }
    }
    return $null
}

function Install-WindowsPython {
    Write-InstallerStep "Python 3.9+ with Tkinter was not found; installing Python."
    Require-WinGet
    & winget install 9NQ7512CXL7T -e --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        Stop-InstallerError `
            -Stage "Installing Python" `
            -Problem "WinGet could not install the official Python install manager." `
            -Action "Check the internet connection and Microsoft Store access, then run this launcher again." `
            -Details "WinGet exit code: $LASTEXITCODE"
    }
    Refresh-ProcessPath
    $manager = Find-PythonManager
    if (-not $manager) {
        Stop-InstallerError `
            -Stage "Installing Python" `
            -Problem "The Python install manager finished installing but could not be started." `
            -Action "Restart Windows once, then run run_windows.bat again."
    }
    & $manager install 3.14
    if ($LASTEXITCODE -ne 0) {
        Stop-InstallerError `
            -Stage "Installing Python runtime" `
            -Problem "Python 3.14 could not be installed." `
            -Action "Check the internet connection, then run this launcher again." `
            -Details "Python install manager exit code: $LASTEXITCODE"
    }
    Refresh-ProcessPath
    if (-not (Find-CompatiblePython)) {
        Stop-InstallerError `
            -Stage "Verifying Python" `
            -Problem "Python installed, but Python 3.9+ with Tkinter still cannot be loaded." `
            -Action "Restart Windows, then run run_windows.bat again. If it persists, repair Python from Windows Installed Apps."
    }
    Write-InstallerSuccess "Python and Tkinter are installed and working."
}

function Find-VideoTools {
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    return ($null -ne $ffmpeg -and $null -ne $ffprobe)
}

function Add-WinGetFFmpegToPath {
    $searchRoots = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages",
        "$env:ProgramFiles\WinGet\Packages"
    ) | Where-Object { Test-Path $_ }
    foreach ($root in $searchRoots) {
        $ffmpeg = Get-ChildItem -Path $root -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ffmpeg -and (Test-Path (Join-Path $ffmpeg.DirectoryName "ffprobe.exe"))) {
            $env:Path = "$($ffmpeg.DirectoryName);$env:Path"
            return
        }
    }
}

function Install-WindowsFFmpeg {
    Write-InstallerStep "FFmpeg or FFprobe was not found; installing the video tools."
    Require-WinGet
    & winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        Stop-InstallerError `
            -Stage "Installing FFmpeg" `
            -Problem "WinGet could not install FFmpeg." `
            -Action "Check the internet connection and available disk space, then run this launcher again." `
            -Details "WinGet exit code: $LASTEXITCODE"
    }
    Refresh-ProcessPath
    if (-not (Find-VideoTools)) {
        Add-WinGetFFmpegToPath
    }
    if (-not (Find-VideoTools)) {
        Stop-InstallerError `
            -Stage "Verifying FFmpeg" `
            -Problem "FFmpeg installed, but ffmpeg.exe and ffprobe.exe could not both be located." `
            -Action "Restart Windows, then run run_windows.bat again."
    }
    Write-InstallerSuccess "FFmpeg and FFprobe are installed and working."
}

function Install-WindowsPrerequisites {
    Write-InstallerStep "Checking Python 3.9+ and Tkinter."
    if (Find-CompatiblePython) {
        Write-InstallerSuccess "Compatible Python and Tkinter found."
    }
    else {
        Install-WindowsPython
    }

    Write-InstallerStep "Checking FFmpeg and FFprobe."
    Refresh-ProcessPath
    if (Find-VideoTools) {
        Write-InstallerSuccess "FFmpeg and FFprobe found."
    }
    else {
        Install-WindowsFFmpeg
    }
    Write-InstallerSuccess "No additional Python packages are required."
}

function Start-MediatovideoConverter {
    Write-InstallerStep "Starting Mediatovideo Converter."
    Set-Location $PSScriptRoot
    $prefixArguments = $script:PythonPrefixArguments
    & $script:PythonExecutable @prefixArguments (Join-Path $PSScriptRoot "run_app.py")
    if ($LASTEXITCODE -ne 0) {
        Stop-InstallerError `
            -Stage "Running Mediatovideo Converter" `
            -Problem "The application stopped unexpectedly." `
            -Action "Read the error shown above. Run this launcher again after correcting it." `
            -Details "Application exit code: $LASTEXITCODE"
    }
    Write-Host ""
    Write-InstallerSuccess "Mediatovideo Converter closed normally."
}

Write-InstallerHeader
Install-WindowsPrerequisites
Start-MediatovideoConverter
