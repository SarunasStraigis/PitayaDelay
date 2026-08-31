# FPGA overlay

STEMlab **125-14** (xc7z010) analog **v0.94** plus a carry-chain TDC. Released images: `fpga/releases/<x.y.z>/pitaya_delay.bit` (see [VERSIONING.md](VERSIONING.md)). Vivado scratch: `fpga/output/` (gitignored).

## Why this map

FemtoSyncTester put the TDC AXI slave at **0x40000000**. That is the stock **housekeeping** window, so SCPI could not map analog. This overlay keeps HK/OSC/ASG/AMS at stock addresses and hangs the TDC on **sys[7] @ 0x40700000** via `tdc_sys_bus` (AXI4-Lite wrapper around `tdc_axi`).

| Bus | Address | Function |
| --- | --- | --- |
| sys[0] | 0x40000000 | Housekeeping (GPIO, ID, …) |
| sys[1] | 0x40100000 | Oscilloscope |
| sys[2] | 0x40200000 | ASG (square LO) |
| sys[3] | — | **PID stubbed** (zeros into DAC mix) |
| sys[4] | 0x40400000 | AMS / PDM |
| sys[5] | 0x40500000 | Daisy |
| sys[6] | — | stub |
| sys[7] | **0x40700000** | **TDC** (`ID = 0x54444331` = `TDC1`) |

Software mmap is 4 KiB at `0x40700000`. Register layout is the FemtoSyncTester map (`sw/tdc_regs.py`).

## GPIO / TDC pins

TDC START/STOP are **inputs** on E1. Default:

| TDC `dio_i` | Name | E1 pin | FPGA |
| --- | --- | --- | --- |
| 8 | DIO7_P | 17 | M14 |
| 9 | DIO7_N | 18 | M15 |

Also wired (selectable via `PUT /api/pins`): DIO0–3 P/N (E1 3–10).

`TDC_INPUT_MASK = 8'b1000_1111` forces DIO0–3 and DIO7 **inputs** on both P and N (HK cannot turn those pads into outputs). Taps are `exp_*_in` after the IOBUF — no extra top-level ports.

TTL: **3.3 V**, pulse width ≳ **8–10 ns**. Do not drive 5 V into these pins.

## What was stubbed / bypassed (7010 fit + timing)

Two 512-tap TDLs plus analog v0.94 do not leave room for everything stock:

1. **PID** — `red_pitaya_pid` is not instantiated. `pid_dat = 0`, `sys[3]` is a bus stub. SCPI PID commands do nothing useful.
2. **Analog EQ** (`rtl/red_pitaya_dfilt1.sv`) — **passthrough**. The DSP equalizer did not close 125 MHz with the TDLs (first impl WNS ≈ −1.9 ns on filter DSPs). DMTD lock-in uses **decimated IQ on the ARM**, not this filter.

TDL placement (after synth, `prj/v0.94/tdc_synth_post.tcl`):

- START: `SLICE_X36Y0:SLICE_X37Y99`
- STOP: `SLICE_X38Y0:SLICE_X39Y99`

False paths: TDL `hit`, `CYINIT`, thermo capture, `rst_cap_d` → thermo, scope filter cfg. Edge FFs get `set_max_delay 6 ns` from DIO.

## Timing (known good bit)

| Stage | WNS |
| --- | --- |
| First impl (EQ DSPs still in) | −1.875 ns |
| Passthrough EQ, routed | −0.028 ns (AXI–XADC IP path) |
| Extra `phys_opt_design` | **+0.051 ns** |

The bitstream in **`fpga/releases/0.1.0/pitaya_delay.bit`** is that post-phys_opt image (~975 kB compressed).

If a rebuild reports a few tens of picoseconds negative on AXI–XADC only:

```powershell
# from repo root, with a routed checkpoint at
# fpga/RedPitaya-FPGA/prj/v0.94/out/post_route.dcp
& C:\Xilinx\Vivado\2020.1\bin\vivado.bat -mode batch -source fpga\tcl\write_bit_physopt.tcl
```

`write_bit_from_route.tcl` re-STAs with extra false paths and writes a bit only if WNS ≥ 0 (no phys_opt).

## Build

**Vivado 2020.1** is required. `Release_2023.1` analog FPGA uses `systemZ10.tcl` for that version. Newer Vivado is not the lab path.

```powershell
powershell -File fpga\tcl\build.ps1
powershell -File scripts\release.ps1          # copies scratch → fpga/releases/<VERSION>/
python sw\bit_to_bin.py fpga\releases\0.1.0\pitaya_delay.bit fpga\output\pitaya_delay.bin
```

`build.ps1` runs `fpga/RedPitaya-FPGA/red_pitaya_vivado_Z10.tcl` with `tclargs v0.94`, then copies `prj/v0.94/out/red_pitaya.bit` → `fpga/output/pitaya_delay.bit` (scratch). Log: `fpga/output/vivado_build.log` (gitignored). Stage a versioned image with `scripts/release.ps1` before committing.

Sources of truth for our patches (also copied into the vendored tree where the RP script expects them):

| Canonical | Used by Vivado |
| --- | --- |
| `fpga/tdc/rtl/*` | `fpga/RedPitaya-FPGA/prj/v0.94/rtl/` (`tdc_*.v`, `tdc_sys_bus.v`) |
| `fpga/tdc/constr/tdc_tdl.xdc` | `fpga/RedPitaya-FPGA/prj/v0.94/sdc/tdc_tdl.xdc` |
| `fpga/tdc/tcl/synth_post.tcl` | `fpga/RedPitaya-FPGA/prj/v0.94/tdc_synth_post.tcl` |
| `fpga/RedPitaya-FPGA/rtl/red_pitaya_dfilt1.sv` | passthrough EQ |
| `fpga/RedPitaya-FPGA/prj/v0.94/rtl/red_pitaya_top.sv` | TDC instance, GPIO mask, PID stub |

After changing TDC RTL, copy into `prj/v0.94/rtl/` (or keep them in sync) before rebuilding.

## Load on the board

`fpga_manager` wants a **.bin**, not a .bit:

```sh
cp pitaya_delay.bin /lib/firmware/
echo 0 > /sys/class/fpga_manager/fpga0/flags
echo pitaya_delay.bin > /sys/class/fpga_manager/fpga0/firmware
# state → operating
```

`scripts/load_overlay.sh` and `scripts/remote_install.sh` do this and check TDC ID `0x54444331`.

**Never** load stock `v0.94` afterward if you still need TDC. `systemctl start redpitaya_scpi` runs `overlay.sh v0.94` and wipes this image. See [BRINGUP.md](BRINGUP.md).

## Simulation

Icarus / Python models under `fpga/tdc/sim/` (encoder, timestamp, Nutt). Not a full analog+TDC chip sim.
