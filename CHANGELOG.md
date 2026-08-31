# Changelog

## 0.1.0

First combined STEMlab 125-14 overlay and measurement server.

- Analog v0.94 (Red Pitaya `Release_2023.1`) plus carry-chain TDC on **sys[7] @ 0x40700000**.
- PID stubbed; analog EQ passthrough so the 7010 closes timing with two 512-tap TDLs.
- Post-`phys_opt_design` WNS **+0.051 ns** (AXI–XADC was −28 ps before phys_opt).
- REST :8080 / UDP :8081: modes `tdc` | `dmtd` | `hybrid`.
- Default TDC START/STOP: DIO7_P / DIO7_N (E1 17/18).

Image: `fpga/releases/0.1.0/pitaya_delay.bit`.
