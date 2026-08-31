# First commit (and what not to add)

This tree contains a **nested git clone** (`fpga/RedPitaya-FPGA/.git`) from a sparse checkout of [RedPitaya/RedPitaya-FPGA](https://github.com/RedPitaya/RedPitaya-FPGA) tag **`Release_2023.1`**. For a **single** product repo, vendor the sources and drop the nested metadata. Otherwise Git records a gitlink (empty submodule) instead of the RTL.

## Before `git add`

From PowerShell, in the PitayaDelay root:

```powershell
# 1. Do not nest another repository
if (Test-Path fpga\RedPitaya-FPGA\.git) {
  Remove-Item -Recurse -Force fpga\RedPitaya-FPGA\.git
}

# 2. Confirm ignored junk is not staged
git status --ignored
```

Do **not** commit:

| Path | Why |
| --- | --- |
| `fpga/RedPitaya-FPGA/.git/` | Nested repo |
| `fpga/RedPitaya-FPGA/prj/v0.94/.srcs/` | Vivado generated IP dump (huge) |
| `fpga/RedPitaya-FPGA/prj/v0.94/out/` | Checkpoints, reports, `red_pitaya.bit` duplicate |
| `fpga/RedPitaya-FPGA/prj/v0.94/.Xil/` | Vivado temp |
| `fpga/RedPitaya-FPGA/*.log`, `*.jou`, `usage_statistics_webtalk.*` | Tool noise |
| `fpga/output/` | Vivado scratch (including unversioned `.bit`) |
| `__pycache__/`, `*.pyc` | Python |

`.gitignore` already covers those.

## Do commit

- `docs/`, `README.md`, `sw/`, `scripts/`, `rp_app/`, `fpga/tdc/`, `fpga/tcl/`
- Vendored analog FPGA **sources** under `fpga/RedPitaya-FPGA/` (RTL, `prj/v0.94/rtl`, `sdc`, `*.tcl` that are not generated) — **not** `.srcs` / `out`
- Our patches in that tree (`red_pitaya_top.sv`, `red_pitaya_dfilt1.sv`, `tdc_*.v`, `tdc_synth_post.tcl`, `tdc_tdl.xdc`)
- **`fpga/releases/0.1.0/`** (`pitaya_delay.bit` + `SHA256SUMS` + `VERSION`) — not `fpga/output/`
- `VERSION`, `CHANGELOG.md`

## SSH / board address

Factory credentials are `root` / `root`. Examples use `rp-XXXXXX.local` (Red Pitaya mDNS; `XXXXXX` is the last six hex digits of the MAC, also on the sticker). A numeric IP works the same. `scripts/deploy.ps1` does **not** bake in a lab host; pass `-HostName` and `-HostKey`.

Do not add `.env` files or extra credentials.

## Suggested first commit

```powershell
cd C:\Users\sarunas\source\repos\PitayaDelay
git init   # if the folder is not already a repo
git add README.md VERSION CHANGELOG.md NOTICE docs sw scripts rp_app fpga/tdc fpga/tcl fpga/releases .gitignore
git add fpga/RedPitaya-FPGA            # after removing nested .git; respect gitignore
git status                             # review: no .srcs, no out/, no .gitlink
git commit -m "Initial PitayaDelay overlay, server, and docs."
```

Do not force-add ignored Vivado trees (`git add -f` on `.srcs` / `out`).
