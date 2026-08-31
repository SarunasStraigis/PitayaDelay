# PitayaDelay API

Base URL: `http://rp-XXXXXX.local:8080` (or the board IP). UDP **8081**: send any datagram; the reply is the same JSON as `GET /api/latest`.

CORS: `OPTIONS` allowed (`GET`, `PUT`, `POST`).

`GET /` lists endpoints, `"service": "pitaya_delay"`, and `"version"`.

## Health

`GET /api/health`

Typical fields (plus TDC status from the mmap):

| Field | Meaning |
| --- | --- |
| `ok` | TDC ID matched `TDC1` |
| `id` | ASCII from ID register (`TDC1`) |
| `version` | SemVer from the `VERSION` file (`0.1.0`) |
| `tdc_base` | `"0x40700000"` |
| `service` | `"pitaya_delay"` |
| `mode` | current config mode |
| `dmtd_ok` | last lock-in succeeded |
| `dmtd_error` | last SCPI/lock-in exception, or `null` |
| `valid`, `armed`, `seq`, … | TDC snapshot (may be invalid with no TTL) |

If `id` is not `TDC1`, the combined overlay is not loaded (usually stock `v0.94` after `overlay.sh`).

## Config

`GET /api/config`  
`PUT /api/config` — JSON object; omitted keys stay as they were. Response is the full config including derived `lo_hz`, `beat_hz`, `f_osc_over_f_pick`, `ratio_near_integer`.

| Field | Default | Notes |
| --- | --- | --- |
| `mode` | `tdc` | `tdc` \| `dmtd` \| `hybrid` |
| `f_osc` | 65e6 | **Example default.** Your RF (Hz); scales DMTD phase → delay and hybrid unwrap |
| `f_pick` | 100e3 | **Example default.** TTL pick rate; hybrid prefers `f_osc / f_pick` near an integer |
| `harmonic` | 5 | Square LO = `(f_osc + demod_hz) / N` (N is this field) |
| `demod_hz` | 1e3 | **Example default.** Target mixer IF / lock-in beat |
| `out_ch` | 1 | ASG channel 1 or 2 |
| `volt` | 1.0 | Square peak (V) |
| `dec` | `null` (auto) | Scope decimation; `"auto"` clears |
| `zero` | false | Next healthy DMTD burst becomes 0 ps (wrapped). Setting `true` retriggers capture of the offset |
| `gen_enable` | false | Program the square LO |
| `use_fft` | true | NCO follows IN1 FFT near `demod_hz` |
| `scpi_host` | `127.0.0.1` | |
| `scpi_port` | 5000 | |
| `adc_hz` | 125e6 | |

`lo_hz` must be in (0, 50 MHz). Invalid JSON or values → HTTP 400 `{ "error": "..." }`.

Example (set `f_osc` / `harmonic` / `demod_hz` to the bench; these numbers are only a starting point):

```json
{
  "mode": "dmtd",
  "f_osc": 65000000,
  "harmonic": 5,
  "demod_hz": 1000,
  "out_ch": 1,
  "volt": 1.0,
  "gen_enable": true,
  "use_fft": true,
  "zero": false
}
```

## Latest

`GET /api/latest` and UDP 8081.

Always present:

| Field | Meaning |
| --- | --- |
| `mode` | |
| `delay_ps` | Result for the mode (`null` if invalid) |
| `tdc_ps` | Raw TDC (`dt_ps`), or `null` |
| `dmtd_ps` | Wrapped analog delay (after optional zero), or `null` |
| `unwrap_slip` | Hybrid only; else `null` |
| `valid` | Mode-dependent (see below) |
| `dmtd_error` | Last analog exception |
| `f_osc`, `f_pick`, `ratio_near_integer` | |
| TDC fields | `seq`, `dt_ns`, `dt_ps`, `t_start`, `t_stop`, `fine_*`, `flags`, `flag_names`, pins, `armed`, … |

DMTD extras when a burst exists: `dmtd_deg`, `beat_hz`, `rms_a`/`rms_b`, `mag_a`/`mag_b`.

**Validity**

- `tdc`: `delay_ps = tdc_ps`; `valid` from TDC.
- `dmtd`: `delay_ps = dmtd_ps`; `valid` if a burst exists and `dmtd_error` is empty.
- `hybrid`: unwrap; `valid` if both instruments healthy and **not** `unwrap_slip`. Also `hybrid_n`.

`GET /api/wait?timeout_ms=1000` polls until TDC `seq` changes (and `valid`). Sets `wait_timed_out`.

## TDC pins

`GET /api/pins` — table + current start/stop.

`PUT /api/pins` — `{ "start": 8, "stop": 9 }` or names (`"DIO7_P"`). Indices 0–9 as in `tdc_regs.PIN_TABLE`. Defaults 8/9 = E1 17/18.

## TDC calibrate

`GET /api/calibrate` — LUT status.

`POST /api/calibrate` — `{ "n": 5000, "timeout_s": 30 }` (defaults shown). Needs a dense START/STOP source. Writes `/root/tdc/cal.json` unless `--cal-file` was set. HTTP 408 if not enough codes in time.

## Hybrid unwrap

```
frac     = wrap(dmtd_ps / T_osc)          # (−½, ½] RF cycles
n        = round(tdc_ps / T_osc − frac)
delay_ps = (n + frac) * T_osc
```

`unwrap_slip` is true when the **residual before rounding** `|tdc_ps/T − frac − n|` exceeds **¼ RF cycle** (default). That is **not** the tautological “TDC vs hybrid > ½ cycle” check (round() already bounds that). Slip means lost coupling, missed TTL, or swapped analog/TTL pair.

Unit checks: `python sw/test_combine.py`.
