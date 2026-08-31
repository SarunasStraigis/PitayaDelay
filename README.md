# PitayaDelay

One **STEMlab 125-14** FPGA overlay and **one HTTP/UDP API** for a hybrid delay measurement:

| Instrument | Role | Signals |
| --- | --- | --- |
| Analog DMTD | Fine delay (phase inside one RF cycle) | 65 MHz oscillator and 65 MHz pulse-picked amp → mixers → **IN1 / IN2** |
| Carry-chain TDC | Coarse interval (which RF cycle) | 100 kHz picks → TTL **START / STOP** on E1 (default DIO7_P / DIO7_N) |

Each 65 MHz line is **coupled** to its 100 kHz pick (`f_osc / f_pick ≈ 650`). Hybrid unwrap uses TDC to pick the integer RF cycle and DMTD for the fraction. Modes: `tdc` | `dmtd` | `hybrid`.

This repo is standalone (not PhaseLab / DMTD C#, not FemtoSyncTester). TDC RTL is copied from FemtoSyncTester; analog FPGA is vendored Red Pitaya `v0.94` (`Release_2023.1`, Vivado **2020.1**).

| Doc | Contents |
| --- | --- |
| [docs/BRINGUP.md](docs/BRINGUP.md) | Load overlay, SCPI (safe), DMTD / TDC / hybrid tests |
| [docs/API.md](docs/API.md) | REST/UDP, config, latest, pins, cal, unwrap |
| [docs/FPGA.md](docs/FPGA.md) | Address map, GPIO, build, timing, what was stubbed |
| [docs/ANALOG.md](docs/ANALOG.md) | Mixers, ADP-2-1W, LO formula, drift, expansion-board thermal |
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | On-board server, PC monitor, deploy scripts |
| [docs/VERSIONING.md](docs/VERSIONING.md) | SemVer, `fpga/releases/<x.y.z>/`, git tags |
| [docs/GIT.md](docs/GIT.md) | What to commit (first commit) |
| [NOTICE](NOTICE) | Provenance (Red Pitaya FPGA, FemtoSyncTester TDC) |

## Quick start (board already running)

1. Confirm overlay: `http://<pitaya>:8080/api/health` → `"id":"TDC1"`, `"version":"0.1.0"`, `"tdc_base":"0x40700000"`.
2. Start **SCPI without** `systemctl start redpitaya_scpi` (that unit runs `overlay.sh v0.94` and **wipes this image**). On the board:

   ```sh
   sh scripts/start_scpi.sh
   ```

   Afterward, health must still show `TDC1`.
3. On the PC:

   ```
   python sw/monitor.py --url http://10.1.251.79:8080
   ```

   Mode **dmtd**, generator ON, **Apply**. Mixer IFs on IN1/IN2; square LO on OUT1 at `(f_osc + demod) / N`.

Fresh board: [docs/BRINGUP.md](docs/BRINGUP.md) (`scripts/deploy.ps1`).

## Layout

```
PitayaDelay/
  VERSION               SemVer (currently 0.1.0)
  CHANGELOG.md
  docs/                 this documentation
  fpga/
    tdc/                TDC RTL, TDL XDC, synth_post
    tcl/                Vivado helpers (build.ps1)
    output/             scratch build (gitignored)
    releases/<x.y.z>/   known-good pitaya_delay.bit
    RedPitaya-FPGA/     vendored v0.94 + our top/TDC patches
  sw/                   server, lock-in, hybrid unwrap, PC GUI
  scripts/              deploy, overlay load, safe SCPI, release.ps1
  rp_app/               minimal web stub (optional)
```

## Hardware (defaults)

- Board: STEMlab **125-14** (xc7z010), OS 2.x with `fpga_manager`.
- DMTD: external dual mixers, **Mini-Circuits ADP-2-1W** LO split, Pitaya **OUT1** square harmonic LO, IFs on **IN1/IN2** (LV).
- TDC: E1 **pin 17** START (DIO7_P), **pin 18** STOP (DIO7_N), 3.3 V TTL, pulses ≳ 8–10 ns.

## First git commit

Read **[docs/GIT.md](docs/GIT.md)** before `git add`. Remove nested `fpga/RedPitaya-FPGA/.git`. Do not add Vivado `.srcs` / `out` / `.Xil` or `fpga/output/`. Commit **`fpga/releases/0.1.0/pitaya_delay.bit`**.

`scripts/deploy.ps1` has lab defaults (IP, `root`/`root`, that board’s host key). Override with parameters for any other board.

## License / provenance

See [NOTICE](NOTICE). Analog FPGA is [RedPitaya/RedPitaya-FPGA](https://github.com/RedPitaya/RedPitaya-FPGA) tag `Release_2023.1`. TDC interpolator and poll server come from FemtoSyncTester, remapped to **0x40700000**.
