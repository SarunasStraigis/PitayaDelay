# Build combined analog+TDC overlay (v0.94 + tdc_axi on sys[7]).
# Usage (from repo root or this folder):
#   powershell -File fpga\tcl\build.ps1

$ErrorActionPreference = "Stop"

$repo = Split-Path (Split-Path $PSScriptRoot)
$fpgaUp = Join-Path $repo "fpga\RedPitaya-FPGA"
$tcl = Join-Path $fpgaUp "red_pitaya_vivado_Z10.tcl"
if (-not (Test-Path $tcl)) {
    throw "Missing $tcl (clone RedPitaya-FPGA Release_2023.1 into fpga\RedPitaya-FPGA)"
}

$vivadoBat = $null
$candidates = @()
if ($env:XILINX_VIVADO) {
    $candidates += Join-Path $env:XILINX_VIVADO "bin\vivado.bat"
}
$candidates += Get-ChildItem "C:\Xilinx\Vivado" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName "bin\vivado.bat" }

foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) {
        $vivadoBat = $c
        break
    }
}

if (-not $vivadoBat) {
    throw "Vivado not found under C:\Xilinx\Vivado."
}

$outDir = Join-Path $repo "fpga\output"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = Join-Path $outDir "vivado_build.log"
Write-Host "Using $vivadoBat"
Write-Host "Log $log"

Push-Location $fpgaUp
try {
    & $vivadoBat -mode batch -nojournal -nolog -source $tcl -tclargs v0.94
    if ($LASTEXITCODE -ne 0) {
        throw "Vivado failed with exit $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$bit = Join-Path $fpgaUp "prj\v0.94\out\red_pitaya.bit"
if (-not (Test-Path $bit)) {
    throw "Bitstream not found at $bit"
}
Copy-Item $bit (Join-Path $outDir "pitaya_delay.bit") -Force
Write-Host "Wrote $(Join-Path $outDir 'pitaya_delay.bit') (scratch; stage with scripts\release.ps1)"
