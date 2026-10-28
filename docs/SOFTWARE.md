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

Do not run a second process on :8080 (only one `server.py`).

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
| `adasops_sim.py` | kHz-ADASOPS picker simulator (CLI) |
| `adasops_gui.py` | Same sim, tkinter + matplotlib UI |
| `test_combine.py` | Unwrap unit checks (`python sw/test_combine.py`) |
| `test_adasops_sim.py` | Picker / grid / period-clamp checks |

## PC monitor

```powershell
python sw\monitor.py
python sw\monitor.py --url http://rp-XXXXXX.local:8080
```

Polls `/api/health`, `/api/config`, `/api/latest`. Status line includes **version**. **Apply** PUTs config (mode, f_osc, N, demod, volt, OUT channel, generator, FFT NCO). **Zero** sets `zero: true`.

## ADASOPS

Planning and the Stage 0 simulator live in the sibling repo **`../PitayaAdasops`** (not a PitayaDelay mode). Copies of `sw/adasops_*.py` here may remain; treat PitayaAdasops as canonical.

## Deploy scripts

| Script | What it does |
| --- | --- |
| `scripts/deploy.ps1` | Converts `fpga/releases/<VERSION>/pitaya_delay.bit`, `pscp` bin + `sw/*.py` + `VERSION`, remounts `/opt/redpitaya` read-write, installs `rp_app/pitaya_delay` at `/opt/redpitaya/www/apps/pitaya_delay/`, reloads nginx, runs `fpga.sh`, then remounts read-only. Disables `redpitaya_scpi.service`. Requires `-HostName` and `-HostKey`. SSH defaults: `root` / `root`. |
| `scripts/release.ps1` | Copy scratch `fpga/output/*.bit` → `fpga/releases/<VERSION>/` + SHA256. |
| `scripts/remote_install.sh` | Firmware load and start `server.py`. Safe SCPI is started afterward by the menu app's `fpga.sh` (or `start_scpi.sh`). **Does not** `systemctl start redpitaya_scpi`. |
| `scripts/load_overlay.sh` | Copy `.bin` to `/lib/firmware`, fpga_manager, check TDC ID. |
| `scripts/start_scpi.sh` | **Required for durable DMTD.** Stops `redpitaya_scpi`, starts `systemd-run --unit=pitaya-scpi-safe` with `LD_LIBRARY_PATH=/opt/redpitaya/lib`. Verifies TDC ID before and after. |

After reboot: reload overlay, start `server.py`, then `start_scpi.sh`.

## Lock-in notes

- `use_fft: true` (default): NCO frequency is the IN1 FFT peak near the expected beat. A few ppm between RF and Pitaya DAC shifts the IF; the FFT is supposed to follow.
- `zero`: first healthy burst (mag/rms ≳ 0.05 on both channels) becomes 0 ps, still wrapped to ±½ RF period.
- Worker reconnects SCPI if the socket dies (`dmtd_error` on `/api/latest` and `/api/health`).

## Menu app

`rp_app/pitaya_delay/` is the Red Pitaya main-menu tile **Pitaya Delay**. The dashboard lists a tile only when `controllerhf.so` is present (`make` on the board). After deploy, open `http://<board>/pitaya_delay/`. The page polls `/pitaya_delay/api/` (nginx → `server.py` on port 8080). **Start** runs `fpga.sh`: load `pitaya_delay.bin`, start `server.py`, start `pitaya-scpi-safe`. **Stop** stops `server.py` only. `restore_fpga.sh` does not load stock v0.94.

The factory **Remote control** tile still starts `redpitaya_scpi`, which runs `overlay.sh v0.94` and replaces this image. `deploy.ps1` disables that service.
