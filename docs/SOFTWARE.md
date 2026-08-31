# Software

Python 3 on the Pitaya (OS 2.x) and on the PC. On-board lock-in needs **numpy** (`sw/requirements.txt`). The PC GUI is **tkinter** only (stdlib).

## On-board server (`sw/server.py`)

One process, REST **:8080**, UDP **:8081** (any datagram → JSON of `GET /api/latest`).

- TDC: mmap `/dev/mem` at **0x40700000** (`tdc_regs`, `tdc_nutt`).
- DMTD: SCPI to **127.0.0.1:5000** (`dmtd.py`) — acquire IN1/IN2, optional square on OUT1, lock-in (optional FFT NCO near `demod_hz`).
- Hybrid: `combine.hybrid_unwrap` ([API.md](API.md)).

Typical argv (what `remote_install.sh` uses):

```sh
python3 server.py --host 0.0.0.0 --port 8080 --udp-port 8081 --base 0x40700000
```

Useful flags: `--sim` (no FPGA), `--cal-file /root/tdc/cal.json`, `--skew-ns`, `--mode dmtd`. Lock file `/tmp/pitaya_delay.server.lock`. Log: `/tmp/pitaya_delay.log`.

Do not also run `tdc_server.py` on 8080 (same ports, old FemtoSyncTester app).

## Modules

| File | Role |
| --- | --- |
| `server.py` | Unified HTTP/UDP, modes, DMTD worker thread |
| `dmtd.py` | SCPI, square LO, acquire, wrap, lock-in |
| `combine.py` | Hybrid unwrap + `f_osc/f_pick` integer check |
| `tdc_server.py` | TDC mmap, pins, Nutt cal, health (base class for HTTP) |
| `tdc_regs.py` | Register map, E1 pin table |
| `tdc_nutt.py` | Code-density interpolation |
| `version.py` | Reads `VERSION` for `/api/health` |
| `bit_to_bin.py` | Vivado .bit → fpga_manager .bin |
| `monitor.py` | PC tkinter client |
| `test_combine.py` | Unwrap unit checks (`python sw/test_combine.py`) |

## PC monitor

```powershell
python sw\monitor.py
python sw\monitor.py --url http://10.1.251.79:8080
```

Polls `/api/health`, `/api/config`, `/api/latest`. Status line includes **version**. **Apply** PUTs config (mode, f_osc, N, demod, volt, OUT channel, generator, FFT NCO). **Zero** sets `zero: true`.

## Deploy scripts

| Script | What it does |
| --- | --- |
| `scripts/deploy.ps1` | Converts `fpga/releases/<VERSION>/pitaya_delay.bit`, `pscp` bin + `sw/*.py` + `VERSION`. `-Version` override. Defaults: host `10.1.251.79`, `root`/`root`, lab host key. |
| `scripts/release.ps1` | Copy scratch `fpga/output/*.bit` → `fpga/releases/<VERSION>/` + SHA256. |
| `scripts/remote_install.sh` | Firmware load, start `server.py`, **nohup** `scpi-server` (prefer `start_scpi.sh` after). **Does not** `systemctl start redpitaya_scpi`. |
| `scripts/load_overlay.sh` | Copy `.bin` to `/lib/firmware`, fpga_manager, check TDC ID. |
| `scripts/start_scpi.sh` | **Required for durable DMTD.** Stops `redpitaya_scpi`, starts `systemd-run --unit=pitaya-scpi-safe` with `LD_LIBRARY_PATH=/opt/redpitaya/lib`. Verifies TDC ID before and after. |

After reboot: reload overlay, start `server.py`, then `start_scpi.sh`.

## Lock-in notes

- `use_fft: true` (default): NCO frequency is the IN1 FFT peak near the expected beat. A few ppm between RF and Pitaya DAC shows up as beat ≈ 1.16 kHz instead of 1.000 kHz — that is expected; the FFT is supposed to follow.
- `zero`: first healthy burst (mag/rms ≳ 0.05 on both channels) becomes 0 ps, still wrapped to ±½ RF cycle.
- Worker reconnects SCPI if the socket dies (`dmtd_error` on `/api/latest` and `/api/health`).

## Optional web stub

`rp_app/pitaya_delay/` is a minimal Red Pitaya app placeholder (`index.html`, `info.json`). Measurement UI is the PC monitor and the JSON API, not this page.
