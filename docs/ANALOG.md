# Analog DMTD

**Dual-mixer time difference** measures how far two RF signals are apart in time by looking at a slow beat, not at the RF cycle itself.

Both signals go to **mixers** that share one **local oscillator** (usually through a **splitter**, so LO phase is common). Each mixer outputs an IF at a few hundred hertz to a few kilohertz. Those two IFs go to the Pitaya (**IN1** and **IN2**). A lock-in on the IF pair turns the **phase difference** into delay. Precision is that of the analog chain and the lock-in (femtosecond-class on a quiet RF), but the reading wraps every **half RF period** — you do not know *which* cycle you are in.

That wrap is why the TTL TDC exists: Start/Stop edges give a coarse interval with a large range. Hybrid mode needs the analog delay and the TTL delay to be the **same physical lag** (each RF coupled to its pick). Frequencies `f_osc` (RF) and `f_pick` (TTL) are whatever you use; they should be in a near-integer ratio so one pick lines up with an integer number of RF cycles. Software defaults (65 MHz / 100 kHz / 1 kHz beat) are only examples.

## What the Pitaya does

| Port | Role |
| --- | --- |
| **IN1 / IN2** | Mixer IFs (LV jumpers). |
| **OUT1** (or OUT2) | Optional square LO. The DAC Nyquist is 50 MHz, so the square is often a **subharmonic**: `f_lo = (f_osc + demod_hz) / N`. The mixers use a harmonic of that square as LO. Drive mixers properly at the **mixing frequency**; keep the Pitaya/amp linear. |
| E1 TTL | TDC START/STOP — not part of DMTD. |

`GET /api/config` reports `lo_hz` and `beat_hz` from `f_osc`, `N`, and `demod_hz`. Set `f_osc` to **your** RF.

## Drift

What walks the reading is **differential** (the two arms not tracking). Shared LO, shared splitter, and a common IF digitizer already cancel a lot. Keep the splitter and both mixers as **one thermal object** (same box, no extra airflow on one SMA). Match cable type and length on the two RF runs and the two LO runs. Do not isolate one mixer from the other.

Zero the DMTD (`zero: true`) when the delay is **not** sitting on the ±180° wrap. Crossing half a cycle after zero looks like a jump of one full RF period.

If you later put this on a mezzanine: cool the Zynq, keep the analog island isothermal and thermally broken from the SoC. No CAD in this repo.

## SCPI

Stock acquire + ASG work on this overlay **if** SCPI is started **without** `overlay.sh v0.94` ([BRINGUP.md](BRINGUP.md)). FPGA analog EQ is a passthrough; lock-in is ARM IQ on decimated traces.
