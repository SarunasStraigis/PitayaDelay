# Bring-up

Target: STEMlab 125-14 on the LAN (example `10.1.251.79`, `root` / `root`). Overlay **is** analog v0.94 plus TDC; you do not restore stock v0.94 to use DMTD.

## 1. Overlay image

Needs **Vivado 2020.1** only if you rebuild. A known-good bit is already in `fpga/releases/0.1.0/`.

```powershell
cd <PitayaDelay>
powershell -File scripts\deploy.ps1          # uses VERSION (0.1.0)
# powershell -File fpga\tcl\build.ps1        # rebuild scratch into fpga/output/
# powershell -File scripts\release.ps1       # promote scratch to fpga/releases/<VERSION>/
```

If implementation reports a hair of negative WNS on AXI-XADC only, `fpga/tcl/write_bit_physopt.tcl` re-STAs a routed checkpoint and writes the bit (used when WNS was −28 ps; post-phys_opt **+51 ps**). See [FPGA.md](FPGA.md) and [VERSIONING.md](VERSIONING.md).

## 2. Deploy overlay + server

From Windows (PuTTY `plink` / `pscp`). Edit `HostName` / host key / password in `scripts/deploy.ps1` if the board is not the lab default.

```powershell
powershell -File scripts\deploy.ps1
```

That copies the versioned `.bit` (converted to `.bin`), `sw/*.py`, and `VERSION` to `/root/pitaya_delay`, loads the FPGA via sysfs, starts `server.py` on **:8080** (UDP **8081**).

Check:

```powershell
Invoke-RestMethod http://10.1.251.79:8080/api/health
```

Expect `ok=True`, `id=TDC1`, `version=0.1.0`, `tdc_base=0x40700000`. `valid` on TDC may be false until START/STOP pulses exist.

On the board, logs: `/tmp/pitaya_delay.log`. Overlay: `cat /sys/class/fpga_manager/fpga0/state` → `operating`.

Reload only the bit: copy `pitaya_delay.bin` to `/lib/firmware/` and run `scripts/load_overlay.sh` (or the same sysfs writes as in `remote_install.sh`).

## 3. SCPI for analog (DMTD / hybrid)

The on-board server lock-in uses **SCPI on 127.0.0.1:5000**. HK/OSC/ASG addresses are stock, so SCPI works **on this overlay**.

**Do not** `systemctl start redpitaya_scpi`. That unit’s `ExecStartPre` is `overlay.sh v0.94` and **replaces** the combined image. The web SCPI tile often does the same.

Safe start (survives SSH logout):

```sh
# on the Pitaya, from this repo or /tmp after pscp
sh scripts/start_scpi.sh
```

That uses `systemd-run --unit=pitaya-scpi-safe` with `LD_LIBRARY_PATH=/opt/redpitaya/lib`. Confirm:

- `ss -lntp | grep 5000`
- `GET /api/health` still `TDC1` (not a housekeeping ID)

Stop stock SCPI if it was started by mistake, then reload this overlay (`deploy.ps1` or `load_overlay.sh`) and start `pitaya-scpi-safe` again.

## 4. Test DMTD only

Cabling:

- Mixer IFs → **IN1** and **IN2**, LV jumpers.
- Square LO → **OUT1** (optional amp; keep the Pitaya/amp **linear**. Mixer **LO pins** should be hard-switched at **65 MHz**, see [ANALOG.md](ANALOG.md)).
- Splitter (ADP-2-1W) on the LO to both mixers.
- TDC cables not required.

PC GUI:

```powershell
python sw\monitor.py --url http://10.1.251.79:8080
```

Set mode `dmtd`, N=5, demod 1000 Hz, f_osc 65e6, generator ON, FFT NCO, **Apply**.

Or PowerShell:

```powershell
$base = "http://10.1.251.79:8080"
Invoke-RestMethod -Method Put -Uri "$base/api/config" -ContentType "application/json" -Body (@{
  mode = "dmtd"; f_osc = 65e6; harmonic = 5; demod_hz = 1e3
  out_ch = 1; volt = 1.0; gen_enable = $true; use_fft = $true; zero = $false
} | ConvertTo-Json)

while ($true) {
  $x = Invoke-RestMethod "$base/api/latest"
  "{0,10:n2} ps  nco={1,8:n2} Hz  magA={2:n4} magB={3:n4}  {4}" -f `
    $x.delay_ps, $x.beat_hz, $x.mag_a, $x.mag_b, $x.dmtd_error
  Start-Sleep -Seconds 1
}
```

**Healthy:** `valid` true, `dmtd_error` empty, `beat_hz` near 1 kHz (often ~1.16 kHz if clocks are a few ppm off — FFT NCO is supposed to follow), `mag_*` not tiny vs `rms_*`. `delay_ps` wraps to ±½ RF cycle (~±7.7 ns at 65 MHz).

**Zero:** GUI **Zero**, or `PUT {"zero": true}`. The next healthy burst becomes 0 ps.

**Errno 111 / connection refused:** SCPI is down. Run `start_scpi.sh`, do not start `redpitaya_scpi.service`.

## 5. Test TDC only

3.3 V TTL, pulses ≳ 8–10 ns, default E1 17 → START, E1 18 → STOP.

```powershell
Invoke-RestMethod -Method Put -Uri "$base/api/config" -ContentType "application/json" -Body '{"mode":"tdc"}'
Invoke-RestMethod "$base/api/latest"
Invoke-RestMethod "$base/api/pins"
```

`delay_ps` tracks `dt_ps` (Nutt). `POST /api/calibrate` with a dense START/STOP source for the code-density LUT (`/root/tdc/cal.json` on the board).

## 6. Test hybrid

Same physical delay on analog and TTL (coupled 65 MHz + 100 kHz pairs). `PUT` `mode=hybrid` with the same DMTD generator fields. `GET /api/latest` should have `delay_ps` (unwrapped), raw `tdc_ps` / `dmtd_ps`, and `unwrap_slip` false on a static delay. Slip means lost coupling, missed TTL, or swapped pair — see [API.md](API.md).

## 7. After reboot

The PL may come up as stock v0.94. Load `pitaya_delay.bin` again (`deploy.ps1` or `load_overlay.sh`), start `server.py` if it is not running, then `start_scpi.sh` for DMTD.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Health `id` not `TDC1` | Stock overlay loaded (`overlay.sh v0.94` / web SCPI) |
| `dmtd_error` connection refused | SCPI not on :5000, or started then killed with SSH |
| Tiny mag, nco stuck at 1000 Hz | No IF, wrong harmonic, LO too small at 65 MHz, saturation |
| Fake ~15384 ps after zero | Wrap through ±180°; zero when not near the wrap |
| TDC timeouts | Pulse too narrow, 5 V into 3.3 V, wrong E1 pins |
| Monitor “Disconnected” | Server not on :8080; firewall; wrong IP |
