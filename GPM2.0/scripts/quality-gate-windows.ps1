[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "app/frontend"
$BackendRoot = Join-Path $ProjectRoot "app/backend"
$TauriRoot = Join-Path $ProjectRoot "app/src-tauri"
$IconVerifier = Join-Path $ProjectRoot "scripts/verify-windows-icon.ps1"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "::group::$Name"
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
        Write-Host "::endgroup::"
    }
}

Invoke-Checked "Tracked LF line endings" $ProjectRoot "python" @(
    "scripts/check_line_endings.py"
)
Invoke-Checked "Frontend tests" $FrontendRoot "npm.cmd" @("test")
Invoke-Checked "Frontend production build" $FrontendRoot "npm.cmd" @("run", "build")

Invoke-Checked "Backend formatting" $BackendRoot "cargo" @("fmt", "--all", "--", "--check")
Invoke-Checked "Backend clippy" $BackendRoot "cargo" @(
    "clippy", "--all-targets", "--locked", "--", "-D", "warnings"
)
Invoke-Checked "Backend tests" $BackendRoot "cargo" @("test", "--locked")

Invoke-Checked "Tauri formatting" $TauriRoot "cargo" @("fmt", "--all", "--", "--check")
Invoke-Checked "Tauri clippy" $TauriRoot "cargo" @(
    "clippy", "--all-targets", "--locked", "--no-default-features", "--", "-D", "warnings"
)
Invoke-Checked "Tauri tests" $TauriRoot "cargo" @(
    "test", "--locked", "--no-default-features"
)
Invoke-Checked "Tauri app build" $TauriRoot "cargo" @(
    "build", "--locked", "--no-default-features"
)

Write-Host "::group::Windows application icon"
try {
    & $IconVerifier `
        -ExpectedIcon (Join-Path $TauriRoot "icons/icon.ico") `
        -ExecutablePath (Join-Path $TauriRoot "target/debug/gpm_next_desktop.exe")
}
finally {
    Write-Host "::endgroup::"
}

Write-Host "GPM2.0 Windows quality gate passed."
