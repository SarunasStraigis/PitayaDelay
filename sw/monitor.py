#!/usr/bin/env python3
"""PC GUI to test PitayaDelay (DMTD / TDC / hybrid) over HTTP :8080.

  python sw/monitor.py
  python sw/monitor.py --url http://10.1.251.79:8080
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox
import urllib.error
import urllib.request

DEFAULT_URL = "http://10.1.251.79:8080"
POLL_S = 0.4
HIST_N = 80


def get_json(url: str, timeout: float = 2.5) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def put_json(url: str, payload: dict, timeout: float = 4.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fmt(v, spec: str, empty: str = "—") -> str:
    if v is None or v == "":
        return empty
    try:
        return format(float(v), spec)
    except (TypeError, ValueError):
        return str(v)


def parse_hz(text: str) -> float:
    return float(str(text).strip().replace(",", ""))


class Monitor(tk.Tk):
    def __init__(self, url: str):
        super().__init__()
        self.title("Pitaya Delay")
        self.geometry("720x620")
        self.minsize(640, 560)

        self.url = tk.StringVar(value=url.rstrip("/"))
        self.status = tk.StringVar(value="Starting…")
        self.delay = tk.StringVar(value="—")
        self.sub = tk.StringVar(value="")
        self.detail = tk.StringVar(value="")
        self.stats = tk.StringVar(value="")
        self.err = tk.StringVar(value="")

        self.mode = tk.StringVar(value="dmtd")
        self.f_osc = tk.StringVar(value="65e6")
        self.harmonic = tk.StringVar(value="5")
        self.demod = tk.StringVar(value="1000")
        self.volt = tk.StringVar(value="1.0")
        self.out_ch = tk.StringVar(value="1")
        self.gen_enable = tk.BooleanVar(value=True)
        self.use_fft = tk.BooleanVar(value=True)

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._hist: deque[float] = deque(maxlen=HIST_N)
        self._pending: dict | None = None
        self._busy = False

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._poll, daemon=True).start()
        self.after(80, self._drain)
        self.after(200, self._load_config)

    def _base(self) -> str:
        return self.url.get().rstrip("/")

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill=tk.X, **pad)
        ttk.Label(top, text="Server").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.url, width=36).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(top, text="Apply config", command=self._apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Zero", command=self._zero).pack(side=tk.LEFT)

        ttk.Label(self, textvariable=self.status).pack(anchor=tk.W, padx=10)

        cfg = ttk.LabelFrame(self, text="DMTD")
        cfg.pack(fill=tk.X, padx=10, pady=6)
        r0 = ttk.Frame(cfg)
        r0.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(r0, text="mode").pack(side=tk.LEFT)
        ttk.Combobox(
            r0, textvariable=self.mode, values=("tdc", "dmtd", "hybrid"), width=8, state="readonly"
        ).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r0, text="f_osc").pack(side=tk.LEFT)
        ttk.Entry(r0, textvariable=self.f_osc, width=10).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r0, text="N").pack(side=tk.LEFT)
        ttk.Entry(r0, textvariable=self.harmonic, width=5).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(r0, text="demod Hz").pack(side=tk.LEFT)
        ttk.Entry(r0, textvariable=self.demod, width=8).pack(side=tk.LEFT, padx=4)

        r1 = ttk.Frame(cfg)
        r1.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Label(r1, text="OUT").pack(side=tk.LEFT)
        ttk.Combobox(r1, textvariable=self.out_ch, values=("1", "2"), width=4, state="readonly").pack(
            side=tk.LEFT, padx=(4, 12)
        )
        ttk.Label(r1, text="Vpk").pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.volt, width=6).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Checkbutton(r1, text="generator ON", variable=self.gen_enable).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(r1, text="FFT NCO", variable=self.use_fft).pack(side=tk.LEFT)

        ttk.Label(self, text="delay_ps", font=("Segoe UI", 10)).pack(anchor=tk.W, padx=10)
        ttk.Label(self, textvariable=self.delay, font=("Consolas", 28)).pack(anchor=tk.W, padx=10)
        ttk.Label(self, textvariable=self.sub, font=("Consolas", 11)).pack(anchor=tk.W, padx=10)
        ttk.Label(self, textvariable=self.detail, font=("Consolas", 10)).pack(anchor=tk.W, padx=10)
        ttk.Label(self, textvariable=self.stats, font=("Consolas", 10)).pack(anchor=tk.W, padx=10)
        ttk.Label(self, textvariable=self.err, foreground="#a40000").pack(anchor=tk.W, padx=10)

        self.canvas = tk.Canvas(self, height=120, background="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(
            self,
            text="LO = (f_osc + demod) / N on OUT. Mixer IFs on IN1/IN2. "
            "Do not systemctl start redpitaya_scpi (that reloads stock v0.94).",
            wraplength=680,
            foreground="#555",
        ).pack(anchor=tk.W, padx=10, pady=(0, 8))

    def _on_close(self) -> None:
        self._stop.set()
        self.destroy()

    def _load_config(self) -> None:
        def work():
            try:
                cfg = get_json(self._base() + "/api/config")
            except Exception as exc:
                self._push(status="Config load failed: %s" % exc)
                return
            self._push(cfg=cfg)

        threading.Thread(target=work, daemon=True).start()

    def _apply(self) -> None:
        if self._busy:
            return
        try:
            body = {
                "mode": self.mode.get(),
                "f_osc": parse_hz(self.f_osc.get()),
                "harmonic": int(self.harmonic.get()),
                "demod_hz": parse_hz(self.demod.get()),
                "out_ch": int(self.out_ch.get()),
                "volt": float(self.volt.get()),
                "gen_enable": bool(self.gen_enable.get()),
                "use_fft": bool(self.use_fft.get()),
            }
        except ValueError as exc:
            messagebox.showerror("Config", str(exc))
            return
        self._busy = True
        self.status.set("Applying…")

        def work():
            try:
                cfg = put_json(self._base() + "/api/config", body)
                with self._lock:
                    self._hist.clear()
                self._push(cfg=cfg, status="Config applied. LO %.6f MHz" % (cfg.get("lo_hz", 0) / 1e6))
            except Exception as exc:
                self._push(status="Apply failed: %s" % exc)
            finally:
                self._busy = False

        threading.Thread(target=work, daemon=True).start()

    def _zero(self) -> None:
        def work():
            try:
                put_json(self._base() + "/api/config", {"zero": True})
                with self._lock:
                    self._hist.clear()
                self._push(status="Zero armed — next healthy DMTD burst becomes 0 ps")
            except Exception as exc:
                self._push(status="Zero failed: %s" % exc)

        threading.Thread(target=work, daemon=True).start()

    def _push(self, **kwargs) -> None:
        with self._lock:
            self._pending = kwargs if self._pending is None else {**self._pending, **kwargs}

    def _drain(self) -> None:
        with self._lock:
            pending = self._pending
            self._pending = None
            hist = list(self._hist)
        if pending:
            if "cfg" in pending:
                self._fill_cfg(pending["cfg"])
            if "status" in pending:
                self.status.set(pending["status"])
            snap = pending.get("snap")
            if snap is not None:
                self._show_snap(snap, hist)
        self._draw(hist)
        self.after(80, self._drain)

    def _fill_cfg(self, cfg: dict) -> None:
        if not cfg:
            return
        if cfg.get("mode"):
            self.mode.set(str(cfg["mode"]))
        if cfg.get("f_osc") is not None:
            self.f_osc.set(("%g" % cfg["f_osc"]))
        if cfg.get("harmonic") is not None:
            self.harmonic.set(str(int(cfg["harmonic"])))
        if cfg.get("demod_hz") is not None:
            self.demod.set("%g" % cfg["demod_hz"])
        if cfg.get("volt") is not None:
            self.volt.set("%g" % cfg["volt"])
        if cfg.get("out_ch") is not None:
            self.out_ch.set(str(int(cfg["out_ch"])))
        if "gen_enable" in cfg:
            self.gen_enable.set(bool(cfg["gen_enable"]))
        if "use_fft" in cfg:
            self.use_fft.set(bool(cfg["use_fft"]))

    def _show_snap(self, snap: dict, hist: list[float]) -> None:
        mode = snap.get("mode") or "—"
        delay = snap.get("delay_ps")
        self.delay.set("—" if delay is None else "%+.3f ps" % float(delay))
        self.sub.set(
            "mode %s    DMTD %s ps   %s deg    TDC %s ps"
            % (
                mode,
                fmt(snap.get("dmtd_ps"), "+.3f"),
                fmt(snap.get("dmtd_deg"), "+.3f"),
                fmt(snap.get("tdc_ps"), "+.3f"),
            )
        )
        self.detail.set(
            "nco %s Hz    magA %s  magB %s    rmsA %s  rmsB %s    slip %s"
            % (
                fmt(snap.get("beat_hz"), ".2f"),
                fmt(snap.get("mag_a"), ".4f"),
                fmt(snap.get("mag_b"), ".4f"),
                fmt(snap.get("rms_a"), ".4f"),
                fmt(snap.get("rms_b"), ".4f"),
                {True: "YES", False: "no", None: "—"}.get(snap.get("unwrap_slip"), str(snap.get("unwrap_slip"))),
            )
        )
        if len(hist) >= 2:
            mean = sum(hist) / len(hist)
            var = sum((x - mean) ** 2 for x in hist) / (len(hist) - 1)
            self.stats.set("last %d:  mean %+ .3f ps   rms %.3f ps" % (len(hist), mean, math.sqrt(var)))
        else:
            self.stats.set("")
        err = snap.get("dmtd_error")
        valid = snap.get("valid")
        bits = []
        if not valid:
            bits.append("valid=false")
        if err:
            bits.append(str(err))
        self.err.set("   ".join(bits))

    def _draw(self, hist: list[float]) -> None:
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        c.create_line(0, h / 2, w, h / 2, fill="#333")
        if len(hist) < 2:
            return
        lo, hi = min(hist), max(hist)
        span = max(hi - lo, 1e-6)
        pts = []
        for i, v in enumerate(hist):
            x = i * (w - 2) / (len(hist) - 1)
            y = h - 4 - (v - lo) / span * (h - 8)
            pts.extend((x, y))
        c.create_line(*pts, fill="#6abf69", width=2, smooth=True)

    def _poll(self) -> None:
        while not self._stop.wait(POLL_S):
            try:
                health = get_json(self._base() + "/api/health")
                snap = get_json(self._base() + "/api/latest")
            except urllib.error.URLError as exc:
                self._push(status="Disconnected: %s" % exc.reason)
                continue
            except Exception as exc:
                self._push(status="Error: %s" % exc)
                continue
            ident = health.get("id")
            ok = health.get("ok")
            ver = health.get("version") or "?"
            mode = health.get("mode") or snap.get("mode")
            self._push(
                status="v%s  ok=%s  FPGA %s  mode=%s  SCPI %s"
                % (
                    ver,
                    ok,
                    ident,
                    mode,
                    "down" if snap.get("dmtd_error") else "up",
                )
            )
            delay = snap.get("delay_ps")
            if snap.get("valid") and delay is not None and not snap.get("dmtd_error"):
                with self._lock:
                    self._hist.append(float(delay))
            self._push(snap=snap)


def main() -> int:
    p = argparse.ArgumentParser(description="PitayaDelay test GUI")
    p.add_argument("--url", default=DEFAULT_URL)
    args = p.parse_args()
    app = Monitor(args.url)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
