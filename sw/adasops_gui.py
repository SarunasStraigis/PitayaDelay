#!/usr/bin/env python3
"""Desktop UI for the kHz-ADASOPS picker simulator.

  pip install numpy matplotlib
  python sw/adasops_gui.py
"""

from __future__ import annotations

import csv
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import adasops_sim as S

try:
    import matplotlib

    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except ImportError as exc:  # pragma: no cover
    raise SystemExit("adasops_gui needs matplotlib: pip install matplotlib") from exc


PS = S.PS
MS = S.MS


class AdasopsGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ADASOPS picker sim")
        self.geometry("1180x780")
        self.minsize(980, 680)

        self.preset = tk.StringVar(value=next(iter(S.PRESETS)))
        self.f1 = tk.StringVar(value="65.012345e6")
        self.f2 = tk.StringVar(value="65.487211e6")
        self.f_trig = tk.StringVar(value="1000")
        self.window = tk.StringVar(value="0.10")
        self.target_ps = tk.StringVar(value="20")
        self.shots = tk.StringVar(value="400")
        self.tdc_ps = tk.StringVar(value="15")
        self.packet = tk.StringVar(value="4000")
        self.wander = tk.StringVar(value="0")
        self.seed = tk.StringVar(value="1")
        self.use_tdc = tk.BooleanVar(value=False)
        self.pairing = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Set frequencies and Run.")
        self.summary = tk.StringVar(value="")
        self.grid_txt = tk.StringVar(value="")

        self._result: S.SimResult | None = None
        self._busy = False
        self._build()
        self._apply_preset(run=False)

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        top = ttk.Frame(self)
        top.pack(fill=tk.X, **pad)
        ttk.Label(top, text="Preset").pack(side=tk.LEFT)
        box = ttk.Combobox(
            top,
            textvariable=self.preset,
            values=list(S.PRESETS),
            width=42,
            state="readonly",
        )
        box.pack(side=tk.LEFT, padx=6)
        box.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset(run=False))
        ttk.Button(top, text="Run", command=self._run).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Export CSV", command=self._export).pack(side=tk.LEFT)
        ttk.Label(top, textvariable=self.status).pack(side=tk.LEFT, padx=12)

        cfg = ttk.LabelFrame(self, text="Lasers and picker")
        cfg.pack(fill=tk.X, padx=10, pady=4)
        r0 = ttk.Frame(cfg)
        r0.pack(fill=tk.X, padx=6, pady=4)
        self._entry(r0, "f1 Hz", self.f1, 16)
        self._entry(r0, "f2 Hz", self.f2, 16)
        self._entry(r0, "f_trig", self.f_trig, 8)
        self._entry(r0, "±window", self.window, 6)
        self._entry(r0, "target ps", self.target_ps, 14)

        r1 = ttk.Frame(cfg)
        r1.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._entry(r1, "shots", self.shots, 6)
        self._entry(r1, "TDC σ ps", self.tdc_ps, 6)
        self._entry(r1, "packet", self.packet, 6)
        self._entry(r1, "wander Hz", self.wander, 6)
        self._entry(r1, "seed", self.seed, 5)
        ttk.Checkbutton(r1, text="use TDC estimate", variable=self.use_tdc).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Checkbutton(r1, text="pairing (pump-OFF same T)", variable=self.pairing).pack(
            side=tk.LEFT
        )

        ttk.Label(self, textvariable=self.summary, font=("Consolas", 10)).pack(
            anchor=tk.W, padx=12, pady=(2, 0)
        )
        ttk.Label(
            self, textvariable=self.grid_txt, font=("Consolas", 9), foreground="#444"
        ).pack(anchor=tk.W, padx=12)

        self.fig = Figure(figsize=(11.2, 5.4), dpi=100)
        self.ax_saw = self.fig.add_subplot(2, 2, 1)
        self.ax_hist = self.fig.add_subplot(2, 2, 2)
        self.ax_err = self.fig.add_subplot(2, 2, 3)
        self.ax_t = self.fig.add_subplot(2, 2, 4)
        self.fig.tight_layout(pad=2.2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        ttk.Label(
            self,
            text="Oracle picker uses exact f1, f2. TDC mode fits a noisy 10 MHz packet "
            "then picks with the estimate. Pairing repeats the previous elapsed T "
            "(reference shot). Comma-separated targets cycle (e.g. 0, 20, 1000).",
            wraplength=1100,
            foreground="#555",
        ).pack(anchor=tk.W, padx=10, pady=(0, 8))

        self.bind("<Return>", lambda _e: self._run())

    def _entry(self, parent: ttk.Frame, label: str, var: tk.StringVar, width: int) -> None:
        ttk.Label(parent, text=label).pack(side=tk.LEFT)
        ttk.Entry(parent, textvariable=var, width=width).pack(side=tk.LEFT, padx=(4, 12))

    def _apply_preset(self, run: bool) -> None:
        spec = S.PRESETS[self.preset.get()]
        self.f1.set("%.9g" % spec["f1"])
        self.f2.set("%.9g" % spec["f2"])
        self.window.set("%g" % spec["window_frac"])
        tgt = spec["target_s"]
        if isinstance(tgt, (int, float)):
            self.target_ps.set("%g" % (float(tgt) * PS))
        else:
            self.target_ps.set(", ".join("%g" % (float(x) * PS) for x in tgt))
        self.status.set(spec.get("note", "Preset loaded."))
        if run:
            self._run()

    def _cfg(self) -> S.SimConfig:
        return S.SimConfig(
            f1=float(self.f1.get()),
            f2=float(self.f2.get()),
            f_trig=float(self.f_trig.get()),
            window_frac=float(self.window.get()),
            target_s=S.parse_target_ps(self.target_ps.get()),
            shots=int(float(self.shots.get())),
            use_tdc=bool(self.use_tdc.get()),
            sigma_tdc_s=float(self.tdc_ps.get()) * 1e-12,
            n_packet=int(float(self.packet.get())),
            wander_hz=float(self.wander.get()),
            pairing=bool(self.pairing.get()),
            seed=int(float(self.seed.get())),
        )

    def _run(self) -> None:
        if self._busy:
            return
        try:
            cfg = self._cfg()
        except ValueError as exc:
            messagebox.showerror("Config", str(exc))
            return
        self._busy = True
        self.status.set("Running…")

        def work() -> None:
            try:
                res = S.run_sim(cfg)
            except Exception as exc:
                self.after(0, lambda: self._done(error=str(exc)))
                return
            self.after(0, lambda: self._done(res=res))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, res: S.SimResult | None = None, error: str | None = None) -> None:
        self._busy = False
        if error:
            self.status.set("Failed: %s" % error)
            messagebox.showerror("Sim", error)
            return
        assert res is not None
        self._result = res
        self.status.set("Done.  " + res.grid.note)
        self.summary.set(S.format_summary(res))
        conv = "   ".join(
            "%d/%d=%.2g ps" % (n, d, r)
            for (n, d), r in zip(res.grid.convergents[:8], res.grid.resolutions_ps[:8])
        )
        self.grid_txt.set("convergents  " + conv)
        self._draw(res)

    def _draw(self, res: S.SimResult) -> None:
        mask = res.signal_mask
        if not np.any(mask):
            mask = np.ones(res.error_s.size, dtype=bool)
        err_ps = res.error_s[mask] * PS
        t1_ms = res.t1_period_s[mask] * MS
        k = np.nonzero(mask)[0]

        m, saw = S.sawtooth_trace(res.cfg.f1, res.cfg.f2, res.cfg.phi, 350)
        for ax in (self.ax_saw, self.ax_hist, self.ax_err, self.ax_t):
            ax.clear()

        self.ax_saw.plot(m, saw * PS, color="#2e7d32", lw=1.0)
        self.ax_saw.set_title("Oscillator delay sawtooth")
        self.ax_saw.set_xlabel("L2 pulse")
        self.ax_saw.set_ylabel("delay vs prev L1 (ps)")

        self.ax_hist.hist(err_ps, bins=min(40, max(10, err_ps.size // 8)), color="#1565c0", edgecolor="white")
        self.ax_hist.axvline(0.0, color="#333", lw=1)
        self.ax_hist.set_title("Achieved − target (signal shots)")
        self.ax_hist.set_xlabel("error (ps)")

        self.ax_err.plot(k, err_ps, ".", color="#6a1b9a", ms=3)
        self.ax_err.axhline(0.0, color="#333", lw=1)
        self.ax_err.set_title("Error vs shot")
        self.ax_err.set_xlabel("shot")
        self.ax_err.set_ylabel("ps")

        self.ax_t.plot(err_ps, t1_ms, ".", color="#c62828", ms=3)
        self.ax_t.set_title("Amplifier period T vs delay error")
        self.ax_t.set_xlabel("error (ps)")
        self.ax_t.set_ylabel("T1 (ms)")

        self.fig.tight_layout(pad=2.2)
        self.canvas.draw_idle()

    def _export(self) -> None:
        if self._result is None:
            messagebox.showinfo("Export", "Run a sim first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="adasops_sim.csv",
        )
        if not path:
            return
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "k",
                    "role",
                    "target_ps",
                    "delay_ps",
                    "error_ps",
                    "n",
                    "m",
                    "T1_ms",
                    "T2_ms",
                ]
            )
            for sh in self._result.shots:
                w.writerow(
                    [
                        sh.k,
                        sh.role,
                        sh.target_s * PS,
                        sh.delay_s * PS,
                        sh.error_s * PS,
                        sh.n,
                        sh.m,
                        sh.t1_period_s * MS,
                        sh.t2_period_s * MS,
                    ]
                )
        self.status.set("Wrote %s" % path)


def main() -> int:
    app = AdasopsGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
