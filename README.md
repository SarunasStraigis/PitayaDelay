# PitayaDelay

A **STEMlab 125-14** delay meter: **femtosecond-class precision** from analog DMTD, and a **wide unambiguous range** from TTL timestamps. One FPGA overlay, one HTTP/UDP API.

You compare two related signals (two clocks, a reference and a device under test, two arms of a splitter, …). DMTD reads the delay *inside one RF cycle* with a lock-in on mixer IFs. A carry-chain TDC reads Start→Stop on 3.3 V TTL and covers many cycles (microseconds, not one RF period). In **hybrid** mode the two are combined: TDC chooses the cycle, DMTD fills in the fraction.

Frequencies are **configuration**, not hardware constants. The software defaults (65 MHz RF, 100 kHz picks, 1 kHz beat) are only examples.

| Path | What it does |
| --- | --- |
| **DMTD** | Dual mixers + shared LO (splitter). Beat notes → Pitaya **IN1 / IN2**. Phase difference → delay wrapped to ±½ RF period, at lock-in precision. |
| **TDC** | TTL **START / STOP** on E1 (default DIO7_P / DIO7_N). Carry-chain interpolator; range is large, precision coarser than DMTD. |
| **Hybrid** | Same physical delay on analog and TTL (each RF coupled to its pick). Unwrap: integer cycles from TDC, fraction from DMTD. |

Modes: `tdc` | `dmtd` | `hybrid`.

Analog FPGA is vendored Red Pitaya `v0.94` (`Release_2023.1`, Vivado **2020.1**). The TDC sits on **sys[7] @ 0x40700000** so housekeeping and SCPI keep their stock map.

| Doc | Contents |
| --- | --- |
| [docs/BRINGUP.md](docs/BRINGUP.md) | Load overlay, SCPI (safe), DMTD / TDC / hybrid tests |
| [docs/API.md](docs/API.md) | REST/UDP, config, latest, pins, cal, unwrap |
| [docs/FPGA.md](docs/FPGA.md) | Address map, GPIO, build, timing, what was stubbed |
| [docs/ANALOG.md](docs/ANALOG.md) | What DMTD is, Pitaya I/O, coupling, drift |
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | On-board server, PC monitor, deploy scripts |
| [docs/VERSIONING.md](docs/VERSIONING.md) | SemVer, `fpga/releases/<x.y.z>/`, git tags |
| [docs/GIT.md](docs/GIT.md) | What to commit (first commit) |
| [NOTICE](NOTICE) | Provenance (Red Pitaya FPGA) |

## Quick start (board already running)

1. Confirm overlay: `http://rp-XXXXXX.local:8080/api/health` → `"id":"TDC1"`, `"version":"0.1.0"`, `"tdc_base":"0x40700000"`.
2. Start **SCPI without** `systemctl start redpitaya_scpi` (that unit runs `overlay.sh v0.94` and **wipes this image**). On the board:

   ```sh
   sh scripts/start_scpi.sh
   ```

   Afterward, health must still show `TDC1`.
3. On the PC:

   ```
   python sw/monitor.py --url http://rp-XXXXXX.local:8080
   ```

   Set **f_osc** to your RF, mode **dmtd**, generator ON, **Apply**. Mixer IFs on IN1/IN2; optional square LO on OUT1 at `(f_osc + demod) / N`.

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

## Hardware

- Board: STEMlab **125-14** (xc7z010), OS 2.x with `fpga_manager`.
- DMTD: external dual-mixer setup (two mixers, LO splitter, IFs into **IN1 / IN2**, LV). Optional LO from Pitaya **OUT1**.
- TDC: E1 **pin 17** START (DIO7_P), **pin 18** STOP (DIO7_N) by default; 3.3 V TTL, pulses ≳ 8–10 ns.

## First git commit

Read **[docs/GIT.md](docs/GIT.md)** before `git add`. Remove nested `fpga/RedPitaya-FPGA/.git`. Do not add Vivado `.srcs` / `out` / `.Xil` or `fpga/output/`. Commit **`fpga/releases/0.1.0/pitaya_delay.bit`**.

SSH factory default is `root` / `root`. Address the board as `rp-XXXXXX.local` (hostname on the sticker, last six MAC digits) or its IP. `scripts/deploy.ps1` requires `-HostName` and `-HostKey` (no board baked in).

## License / provenance

See [NOTICE](NOTICE). Analog FPGA is [RedPitaya/RedPitaya-FPGA](https://github.com/RedPitaya/RedPitaya-FPGA) tag `Release_2023.1`. TDC and the measurement server live in this repository (TDC at **0x40700000**).
