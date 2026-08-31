# Copy a built bitstream into fpga/releases/<VERSION>/.
# Does not run Vivado. Build first (fpga\tcl\build.ps1), then:
#   powershell -File scripts\release.ps1
#   powershell -File scripts\release.ps1 -Version 0.1.1 -Force

param(
    [string]$Version = "",
    [string]$Bit = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot

if (-not $Version) {
    $Version = (Get-Content (Join-Path $Repo "VERSION") -Raw).Trim().Split("`n")[0].Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+') {
    throw "VERSION must look like 0.1.0, got '$Version'"
}

if (-not $Bit) {
    $Bit = Join-Path $Repo "fpga\output\pitaya_delay.bit"
}
if (-not (Test-Path $Bit)) {
    throw "Missing $Bit. Build first: powershell -File fpga\tcl\build.ps1"
}

$destDir = Join-Path $Repo "fpga\releases\$Version"
$destBit = Join-Path $destDir "pitaya_delay.bit"
if ((Test-Path $destBit) -and -not $Force) {
    throw "$destBit already exists. Bump VERSION or pass -Force to replace this release."
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item $Bit $destBit -Force
Copy-Item (Join-Path $Repo "VERSION") (Join-Path $destDir "VERSION") -Force

$hash = (Get-FileHash -Algorithm SHA256 $destBit).Hash.ToLower()
$sums = "$hash  pitaya_delay.bit"
Set-Content -Path (Join-Path $destDir "SHA256SUMS") -Value $sums -Encoding ascii
Write-Host "Staged $destBit"
Write-Host $sums
Write-Host "Next: git add fpga/releases/$Version CHANGELOG.md VERSION && tag v$Version"
