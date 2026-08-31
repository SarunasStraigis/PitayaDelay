# Deploy a versioned overlay + server to a STEMlab (default 10.1.251.79).
# Requires PuTTY plink/pscp.
#   powershell -File scripts\deploy.ps1
#   powershell -File scripts\deploy.ps1 -Version 0.1.0

param(
    [string]$HostName = "10.1.251.79",
    [string]$User = "root",
    [string]$Password = "root",
    [string]$HostKey = "SHA256:eznXsX+n6Gt4L6zNjUeAIsfpnDm1tHgig4Opmw1whKs",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Version) {
    $Version = (Get-Content (Join-Path $Repo "VERSION") -Raw).Trim().Split("`n")[0].Trim()
}

$ReleaseBit = Join-Path $Repo "fpga\releases\$Version\pitaya_delay.bit"
$ScratchBit = Join-Path $Repo "fpga\output\pitaya_delay.bit"
if (Test-Path $ReleaseBit) {
    $Bit = $ReleaseBit
    Write-Host "Deploying release $Version from $Bit"
} elseif (Test-Path $ScratchBit) {
    $Bit = $ScratchBit
    Write-Warning "No fpga/releases/$Version/pitaya_delay.bit; using unversioned scratch $Bit"
} else {
    throw "Missing overlay for $Version. Stage one: powershell -File scripts\release.ps1"
}

$Bin = Join-Path $Repo "fpga\output\pitaya_delay.bin"
$RemoteSh = Join-Path $PSScriptRoot "remote_install.sh"
New-Item -ItemType Directory -Force -Path (Split-Path $Bin) | Out-Null

$plink = (Get-Command plink -ErrorAction SilentlyContinue).Source
$pscp = (Get-Command pscp -ErrorAction SilentlyContinue).Source
if (-not $plink) { $plink = "C:\Program Files\PuTTY\plink.exe" }
if (-not $pscp) { $pscp = "C:\Program Files\PuTTY\pscp.exe" }

python (Join-Path $Repo "sw\bit_to_bin.py") $Bit $Bin
if ($LASTEXITCODE -ne 0) { throw "bit_to_bin failed" }

$remote = "${User}@${HostName}"
$argsCommon = @("-batch", "-pw", $Password, "-hostkey", $HostKey)
& $pscp @argsCommon $Bin "${remote}:/root/pitaya_delay.bin"
foreach ($f in @("server.py", "dmtd.py", "combine.py", "tdc_server.py", "tdc_regs.py", "tdc_nutt.py", "bit_to_bin.py", "version.py")) {
    & $pscp @argsCommon (Join-Path $Repo "sw\$f") "${remote}:/root/$f"
}
& $pscp @argsCommon (Join-Path $Repo "VERSION") "${remote}:/root/VERSION"
& $pscp @argsCommon $RemoteSh "${remote}:/tmp/remote_install.sh"
& $plink @argsCommon $remote "sed -i 's/\r`$//' /tmp/remote_install.sh && sh /tmp/remote_install.sh"
