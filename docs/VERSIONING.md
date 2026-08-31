# Versioning

One SemVer for the **overlay + server** that ship together. FPGA ID stays `TDC1`; the human version is the `VERSION` file and `GET /api/health` → `version`.

| Part | When it bumps |
| --- | --- |
| **MAJOR** | Address map or JSON API break (TDC base, register layout, removed fields) |
| **MINOR** | New capability (mode, pins, hybrid, SCPI behaviour) |
| **PATCH** | Rebuild, timing fix, lock-in tweak, docs that ship with a new bit |

Git tag: `v0.1.0` (same number as `VERSION`).

## Where images live

| Path | Role | Git |
| --- | --- | --- |
| `fpga/output/` | Scratch from Vivado | **ignored** |
| `fpga/releases/<x.y.z>/pitaya_delay.bit` | Known-good overlay | **committed** |
| `fpga/releases/<x.y.z>/SHA256SUMS` | Hash of that `.bit` | committed |
| `.bin` | `fpga_manager` payload | never committed (`bit_to_bin.py`) |

Do not commit an unversioned `fpga/output/pitaya_delay.bit`. Deploy uses the release folder matching `VERSION` (override `-Version`).

## Cut a release

1. Bump the root `VERSION` file and add a `CHANGELOG.md` section.
2. Rebuild if RTL or constraints changed: `powershell -File fpga\tcl\build.ps1`
3. Stage the bit (refuses to overwrite unless `-Force`):

   ```powershell
   powershell -File scripts\release.ps1
   ```

4. Commit `VERSION`, `CHANGELOG.md`, and `fpga/releases/<x.y.z>/`.
5. Tag `v<x.y.z>`.

GitHub Releases are optional later if the tree collects many 1 MB bits; the in-repo folders work offline and match `deploy.ps1`.

## On the board

`scripts/deploy.ps1` copies `VERSION` next to `server.py`. Health reports that string. Loading stock `v0.94` does not change this file — still check FPGA `id` is `TDC1`.
