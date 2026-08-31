#!/usr/bin/env python3
"""Unified TDC + DMTD + hybrid delay server (REST :8080, UDP :8081)."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from socketserver import BaseRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import combine
import dmtd
import tdc_server
from version import VERSION
from tdc_regs import DEFAULT_BASE
from tdc_server import (
    SimTdc,
    ThreadingHTTPServer,
    ThreadingUDPServer,
    acquire_instance_lock,
    apply_skew,
    parse_base,
    port_in_use,
)


MODES = ("tdc", "dmtd", "hybrid")
SERVER_LOCK_PATH = "/tmp/pitaya_delay.server.lock"
tdc_server.SERVER_LOCK_PATH = SERVER_LOCK_PATH


def default_config() -> dict:
    return {
        "mode": "tdc",
        "f_osc": 65e6,
        "f_pick": 100e3,
        "harmonic": 5,
        "demod_hz": 1e3,
        "out_ch": 1,
        "volt": 1.0,
        "dec": None,
        "zero": False,
        "gen_enable": False,
        "use_fft": True,
        "scpi_host": "127.0.0.1",
        "scpi_port": 5000,
        "adc_hz": dmtd.ADC_HZ_DEFAULT,
    }


class DelayEngine:
    def __init__(self, tdc, skew_ns: float = 0.0, sim: bool = False):
        self.tdc = tdc
        self.skew_ns = float(skew_ns)
        self.sim = bool(sim)
        self._lock = threading.Lock()
        self.cfg = default_config()
        self._dmtd: Optional[dict] = None
        self._dmtd_err: Optional[str] = None
        self._zero_ps = 0.0
        self._have_zero = False
        self._scpi: Optional[dmtd.Scpi] = None
        self._applied = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._close_scpi()
        close = getattr(self.tdc, "close", None)
        if callable(close):
            close()

    def get_config(self) -> dict:
        with self._lock:
            out = dict(self.cfg)
        out["lo_hz"], out["beat_hz"] = dmtd.lo_and_beat(
            out["f_osc"], int(out["harmonic"]), out["demod_hz"]
        )
        ratio_ok = combine.ratio_near_integer(out["f_osc"], out["f_pick"])
        out["f_osc_over_f_pick"] = (
            None if out["f_pick"] <= 0 else out["f_osc"] / out["f_pick"]
        )
        out["ratio_near_integer"] = ratio_ok
        return out

    def set_config(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("JSON object required")
        with self._lock:
            cfg = dict(self.cfg)
            if "mode" in body:
                mode = str(body["mode"]).strip().lower()
                if mode not in MODES:
                    raise ValueError("mode must be tdc, dmtd, or hybrid")
                cfg["mode"] = mode
            for key, cast in (
                ("f_osc", float),
                ("f_pick", float),
                ("harmonic", int),
                ("demod_hz", float),
                ("out_ch", int),
                ("volt", float),
                ("adc_hz", float),
                ("scpi_port", int),
            ):
                if key in body and body[key] is not None:
                    cfg[key] = cast(body[key])
            if "dec" in body:
                cfg["dec"] = None if body["dec"] in (None, "", "auto") else int(body["dec"])
            if "zero" in body:
                cfg["zero"] = bool(body["zero"])
                if cfg["zero"]:
                    self._have_zero = False
                    self._zero_ps = 0.0
            if "gen_enable" in body:
                cfg["gen_enable"] = bool(body["gen_enable"])
            if "use_fft" in body:
                cfg["use_fft"] = bool(body["use_fft"])
            if "scpi_host" in body and body["scpi_host"]:
                cfg["scpi_host"] = str(body["scpi_host"])
            if cfg["harmonic"] < 1:
                raise ValueError("harmonic must be >= 1")
            if cfg["out_ch"] not in (1, 2):
                raise ValueError("out_ch must be 1 or 2")
            lo_hz, _beat = dmtd.lo_and_beat(cfg["f_osc"], cfg["harmonic"], cfg["demod_hz"])
            if lo_hz <= 0 or lo_hz >= dmtd.DAC_NYQUIST_HZ:
                raise ValueError("square LO %.6f MHz is outside 0–%.0f MHz" % (lo_hz / 1e6, dmtd.DAC_NYQUIST_HZ / 1e6))
            self.cfg = cfg
            self._applied = None
        return self.get_config()

    def _close_scpi(self) -> None:
        if self._scpi is not None:
            try:
                self._scpi.close()
            except OSError:
                pass
            self._scpi = None

    def _ensure_analog(self, cfg: dict):
        key = (
            cfg["scpi_host"],
            cfg["scpi_port"],
            cfg["f_osc"],
            cfg["harmonic"],
            cfg["demod_hz"],
            cfg["out_ch"],
            cfg["volt"],
            cfg["dec"],
            cfg["gen_enable"],
            cfg["adc_hz"],
        )
        if self._scpi is not None and self._applied == key:
            return self._scpi, cfg["dec"] or dmtd.choose_dec(
                cfg["adc_hz"], dmtd.lo_and_beat(cfg["f_osc"], cfg["harmonic"], cfg["demod_hz"])[1]
            )
        self._close_scpi()
        rp = dmtd.Scpi(cfg["scpi_host"], int(cfg["scpi_port"]))
        lo_hz, beat_hz = dmtd.lo_and_beat(cfg["f_osc"], cfg["harmonic"], cfg["demod_hz"])
        dec = cfg["dec"] if cfg["dec"] is not None else dmtd.choose_dec(cfg["adc_hz"], beat_hz)
        dmtd.configure_acq(rp, dec)
        if cfg["gen_enable"]:
            dmtd.configure_square_lo(rp, lo_hz, cfg["volt"], cfg["out_ch"])
        self._scpi = rp
        self._applied = key
        return rp, dec

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            with self._lock:
                cfg = dict(self.cfg)
            if cfg["mode"] == "tdc":
                continue
            try:
                rp, dec = self._ensure_analog(cfg)
                sample_rate = cfg["adc_hz"] / dec
                _lo, beat_hz = dmtd.lo_and_beat(cfg["f_osc"], cfg["harmonic"], cfg["demod_hz"])
                ch_a, ch_b = dmtd.acquire_pair(rp)
                raw = dmtd.process_block(
                    ch_a, ch_b, sample_rate, beat_hz, cfg["f_osc"], use_fft=cfg["use_fft"]
                )
                delay_ps = dmtd.wrap_ps(raw["diff_ps"], cfg["f_osc"])
                with self._lock:
                    if cfg["zero"] and not self._have_zero:
                        snr_a = raw["mag_a"] / raw["rms_a"] if raw["rms_a"] > 1e-12 else 0.0
                        snr_b = raw["mag_b"] / raw["rms_b"] if raw["rms_b"] > 1e-12 else 0.0
                        if snr_a >= 0.05 and snr_b >= 0.05:
                            self._zero_ps = delay_ps
                            self._have_zero = True
                    if self._have_zero:
                        delay_ps = dmtd.wrap_ps(delay_ps - self._zero_ps, cfg["f_osc"])
                    raw = dict(raw)
                    raw["dmtd_ps"] = delay_ps
                    raw["sample_rate"] = sample_rate
                    raw["dec"] = dec
                    raw["unix_s"] = time.time()
                    self._dmtd = raw
                    self._dmtd_err = None
            except Exception as exc:
                with self._lock:
                    self._dmtd_err = str(exc)
                    self._close_scpi()
                    self._applied = None
                time.sleep(0.5)

    def latest(self) -> dict:
        tdc_snap = apply_skew(self.tdc.snapshot(), self.skew_ns)
        with self._lock:
            cfg = dict(self.cfg)
            dmtd_snap = None if self._dmtd is None else dict(self._dmtd)
            dmtd_err = self._dmtd_err
        mode = cfg["mode"]
        out = dict(tdc_snap)
        out["mode"] = mode
        out["f_osc"] = cfg["f_osc"]
        out["f_pick"] = cfg["f_pick"]
        out["tdc_ps"] = tdc_snap.get("dt_ps")
        out["dmtd_ps"] = None if dmtd_snap is None else dmtd_snap.get("dmtd_ps")
        out["dmtd_deg"] = None if dmtd_snap is None else dmtd_snap.get("diff_deg")
        out["beat_hz"] = None if dmtd_snap is None else dmtd_snap.get("beat_hz")
        out["rms_a"] = None if dmtd_snap is None else dmtd_snap.get("rms_a")
        out["rms_b"] = None if dmtd_snap is None else dmtd_snap.get("rms_b")
        out["mag_a"] = None if dmtd_snap is None else dmtd_snap.get("mag_a")
        out["mag_b"] = None if dmtd_snap is None else dmtd_snap.get("mag_b")
        out["unwrap_slip"] = None
        out["delay_ps"] = None
        out["dmtd_error"] = dmtd_err
        out["ratio_near_integer"] = combine.ratio_near_integer(cfg["f_osc"], cfg["f_pick"])

        if mode == "tdc":
            out["delay_ps"] = out["tdc_ps"]
            out["valid"] = bool(tdc_snap.get("valid"))
        elif mode == "dmtd":
            out["delay_ps"] = out["dmtd_ps"]
            out["valid"] = dmtd_snap is not None and dmtd_err is None
        else:
            tdc_ps = out["tdc_ps"]
            dmtd_ps = out["dmtd_ps"]
            if tdc_ps is None or dmtd_ps is None or not tdc_snap.get("valid") or dmtd_err:
                out["valid"] = False
            else:
                hyb = combine.hybrid_unwrap(float(tdc_ps), float(dmtd_ps), cfg["f_osc"])
                out["delay_ps"] = hyb["delay_ps"]
                out["unwrap_slip"] = hyb["unwrap_slip"]
                out["hybrid_n"] = hyb["n"]
                out["valid"] = not hyb["unwrap_slip"]
        return out

    def health(self) -> dict:
        h = self.tdc.health()
        h["service"] = "pitaya_delay"
        h["version"] = VERSION
        h["mode"] = self.get_config()["mode"]
        h["tdc_base"] = "0x%08X" % getattr(self.tdc, "base", DEFAULT_BASE)
        with self._lock:
            h["dmtd_ok"] = self._dmtd_err is None and self._dmtd is not None
            h["dmtd_error"] = self._dmtd_err
        return h


class DelayHttpHandler(tdc_server.TdcHttpHandler):
    engine: DelayEngine

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        if path == "/api/latest":
            self._send_json(200, self.engine.latest())
            return
        if path == "/api/wait":
            timeout_ms = 1000
            if "timeout_ms" in qs:
                try:
                    timeout_ms = max(0, int(qs["timeout_ms"][0]))
                except ValueError:
                    self._send_json(400, {"error": "timeout_ms must be an integer"})
                    return
            first = self.engine.latest()
            deadline = time.monotonic() + timeout_ms / 1000.0
            last = first
            while time.monotonic() < deadline:
                last = self.engine.latest()
                if last.get("valid") and last.get("seq") != first.get("seq"):
                    last = dict(last)
                    last["wait_timed_out"] = False
                    self._send_json(200, last)
                    return
                time.sleep(0.001)
            last = dict(last)
            last["wait_timed_out"] = True
            self._send_json(200, last)
            return
        if path == "/api/config":
            self._send_json(200, self.engine.get_config())
            return
        if path == "/api/health":
            self._send_json(200, self.engine.health())
            return
        if path == "/":
            self._send_json(
                200,
                {
                    "service": "pitaya_delay",
                    "version": VERSION,
                    "endpoints": [
                        "/api/latest",
                        "/api/wait?timeout_ms=1000",
                        "/api/health",
                        "/api/config",
                        "/api/pins",
                        "/api/calibrate",
                    ],
                },
            )
            return
        super().do_GET()

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path != "/api/config":
            super().do_PUT()
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            self._send_json(400, {"error": "invalid JSON"})
            return
        try:
            payload = self.engine.set_config(body)
        except (ValueError, TypeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, payload)


class UdpPollHandler(BaseRequestHandler):
    def handle(self) -> None:
        _data, sock = self.request
        snap = self.server.engine.latest()
        sock.sendto(json.dumps(snap, separators=(",", ":")).encode("utf-8"), self.client_address)


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Red Pitaya TDC+DMTD delay server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--udp-port", type=int, default=8081, help="0 disables UDP poll")
    p.add_argument("--base", default=hex(DEFAULT_BASE), help="TDC register base")
    p.add_argument("--skew-ns", type=float, default=0.0)
    p.add_argument("--cal-file", default=None)
    p.add_argument("--sim", action="store_true")
    p.add_argument("--sim-period-ms", type=float, default=10.0)
    p.add_argument("--sim-dt-ns", type=float, default=1_000_000.0)
    p.add_argument("--mode", choices=MODES, default=None)
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    lock_fd: Optional[int] = None
    if not args.sim:
        if port_in_use(args.host, args.port):
            print("server already listening on %s:%d" % (args.host, args.port), file=sys.stderr)
            return 1
        lock_fd = acquire_instance_lock()
        if lock_fd == -1:
            return 1
    if args.sim:
        device = SimTdc(
            period_s=args.sim_period_ms / 1000.0,
            dt_ns=args.sim_dt_ns,
        )
    else:
        last_err: Optional[BaseException] = None
        device = None
        for _ in range(30):
            try:
                device = tdc_server.FpgaTdc(base=parse_base(args.base), cal_path=args.cal_file)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                time.sleep(0.2)
        if last_err is not None:
            print("FPGA open failed: %s" % last_err, file=sys.stderr, flush=True)
            return 1

    engine = DelayEngine(device, skew_ns=args.skew_ns, sim=args.sim)
    if args.mode:
        engine.set_config({"mode": args.mode})

    DelayHttpHandler.engine = engine
    DelayHttpHandler.device = device
    DelayHttpHandler.skew_ns = args.skew_ns

    httpd = ThreadingHTTPServer((args.host, args.port), DelayHttpHandler)
    httpd.engine = engine
    udp = None
    if args.udp_port:
        udp = ThreadingUDPServer((args.host, args.udp_port), UdpPollHandler)
        udp.engine = engine
        threading.Thread(target=udp.serve_forever, daemon=True).start()

    print(
        "pitaya_delay http://%s:%d  udp %s  tdc_base %s"
        % (args.host, args.port, args.udp_port or "off", args.base),
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    finally:
        httpd.server_close()
        if udp is not None:
            udp.shutdown()
        engine.close()
        if lock_fd not in (None, -1):
            try:
                os.close(lock_fd)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
