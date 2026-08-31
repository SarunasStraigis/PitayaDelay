# Analog DMTD and cabling

Fine delay is a **dual-mixer time difference** at the RF (default 65 MHz). The Pitaya only sees the **IF beat** on IN1/IN2 and generates a **square** harmonic LO on OUT1. Mixers and the LO splitter sit off-board (or on a future mezzanine).

## Signal roles

| Line | Frequency | Where it goes |
| --- | --- | --- |
| Oscillator RF | 65 MHz | Mixer 1 RF |
| PPA RF | 65 MHz | Mixer 2 RF |
| Oscillator pick | 100 kHz TTL | TDC START (E1 17) |
| PPA pick | 100 kHz TTL | TDC STOP (E1 18) |
| Square LO | `(f_osc + demod) / N` | Split → both mixer LO ports |
| Mixer IF | ~`demod` (default 1 kHz) | Pitaya **IN1** and **IN2**, LV jumpers |

The 65 MHz and 100 kHz of each source are **coupled** (`f_osc / f_pick ≈ 650`). Hybrid unwrap needs that; a free-running TDC pair that is not the same delay as the analog pair will set `unwrap_slip`.

## Square LO (harmonic)

The ASG cannot put a clean 65 MHz square on OUT1 (DAC Nyquist 50 MHz). Drive a **lower** square whose **Nth harmonic** is the mixer LO:

```
f_lo = (f_osc + demod_hz) / N
```

Default N = 5 → **13.0002 MHz** for 65 MHz + 1 kHz. The IF is `demod_hz` (1 kHz), not the 13 MHz tone.

**Drive the mixer LO pins hard at 65 MHz.** Level-7/10/13 diode mixers want roughly +7 to +13 dBm **at the mixing frequency**. Do **not** clip the Pitaya or an IF amp at 13 MHz hoping the 5th harmonic will magically appear at the diodes. Either:

- a real 65 MHz LO (preferred for production), or
- a linear amp after OUT1 plus a mixer that still switches on the 5th harmonic (verify with a spectrum analyzer at the LO pin).

Keep the Pitaya/amp **linear**. Overload belongs at the **mixer LO**, not the generator.

`GET /api/config` reports `lo_hz` and `beat_hz` after N and demod.

## Splitter: Mini-Circuits ADP-2-1W

A ferrite 2-way (CD636). At ~60–65 MHz it is a good LO tee:

- ~3.2 dB total loss, isolation ~39 dB
- Phase unbalance ~0.01° typical (~0.4 ps at 65 MHz); datasheet worst-case mid-band 2° is a **static** offset, not drift
- Temperature: ~0.06 ps/°C **differential** from the splitter itself (−40/+85 °C tables)

It is **not** the hour-scale drift bottleneck. Cables and the two mixers usually dominate. Use it as the **LO split**; keep ADP + both mixers as **one thermal object**.

## Drift (what actually moves)

What survives is **differential** (the two arms not tracking). Common LO phase, common Pitaya IF, and a shared splitter already cancel a lot.

- **Temperature / gradients** — main knob. Splitter, both mixers, and short SMA jumpers in the **same** box. Kill drafts. Isolating one mixer from the other usually **creates** drift.
- **Cables** — match type and length on the two RF (and two LO) runs. PTFE ~50–100 ppm/°C: 1 m at 65 MHz is ~5 ns → **~0.3–0.5 ps/°C per unmatched metre**. A long LO cable to only one mixer does not cancel.
- **Pitaya IN1/IN2** — LV, no extra digital EQ (FPGA filter is passthrough). Lock-in is ARM IQ on decimated traces.

Zero the DMTD (`zero: true`) when the delay is **not** sitting on the ±180° wrap. Wrap through half a cycle after zero looks like a ~15 ns jump (`2 × 7.7 ns`).

## Expansion-board thermal (mezzanine)

Cool the **Pitaya**, keep the **analog isothermal**. Drift cares about **gradients and dT/dt**, not how cold the mixers are.

**Two zones:**

1. **Digital / power** — Zynq, DC–DC, any LO power amp that runs warm. Heatsink or a small fan is fine here. FPGA load (TDL + scope) is a real watt-class change; do not put mixers over the SoC.
2. **RF analog island** — ADP-2-1W, both mixers, short LO/RF jumpers, IF filters. One copper lump, **no fan across it**, no extra airflow on one SMA. Thermal **break** from the SoC (slots, plastic standoffs, no copper pour tying the island to the CPU can).

Board habits:

- Shared copper pour under mixers + splitter; screw to an aluminum lid/can (heat capacity).
- Same footprint/orientation for both mixers; **matched** LO and RF traces.
- Still air on the analog can. No per-mixer Peltier or foam “isolation.”

No CAD in this repo — electrical and thermal intent only.

## Pitaya analog front end

- IN1 / IN2: **LV** jumpers for millivolt–volt IFs.
- OUT1 (or OUT2 via `out_ch`): square LO, default 1.0 V peak (`volt` in config).
- Scope decimation: auto unless `dec` is set. Need Nyquist ≳ 5× beat (see `dmtd.choose_dec`).
- Stock SCPI acquire + ASG work on this overlay **if** SCPI is started **without** `overlay.sh v0.94` ([BRINGUP.md](BRINGUP.md)).
