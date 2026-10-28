#!/usr/bin/env python3
"""kHz-ADASOPS pulse-picker simulator (Stage 0).

Two free-running oscillators seed two amplifiers. Each shot, the device may
only fire about one amplifier period later (± window_frac). It chooses the
oscillator pulse pair in that window whose delay is closest to the target.

  python sw/adasops_sim.py --f1 65e6 --f2 65.5e6 --target-ps 20 --shots 400
  python sw/adasops_gui.py
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

PS = 1e12
MS = 1e3


# ---------------------------------------------------------------------------
# Number theory (delay grid from f1/f2)
# ---------------------------------------------------------------------------


def continued_fraction(num: int, den: int, max_terms: int = 24) -> list[int]:
    """Euclid continued-fraction terms of num/den ≥ 0."""
    if den == 0:
        raise ValueError("den must be nonzero")
    num, den = abs(int(num)), abs(int(den))
    terms: list[int] = []
    while den and len(terms) < max_terms:
        q, r = divmod(num, den)
        terms.append(q)
        num, den = den, r
    return terms


def convergents(terms: Sequence[int]) -> list[tuple[int, int]]:
    """Successive convergents (N_m, D_m) of a continued fraction."""
    if not terms:
        return []
    n0, n1 = 1, terms[0]
    d0, d1 = 0, 1
    out = [(n1, d1)]
    for a in terms[1:]:
        n0, n1 = n1, a * n1 + n0
        d0, d1 = d1, a * d1 + d0
        out.append((n1, d1))
    return out


def hz_to_ints(f1: float, f2: float) -> tuple[int, int]:
    """Round frequencies to 1 Hz for the rational model used in the papers."""
    a, b = int(round(f1)), int(round(f2))
    if a <= 0 or b <= 0:
        raise ValueError("frequencies must be positive")
    g = math.gcd(a, b)
    return a // g, b // g


@dataclass(frozen=True)
class GridInfo:
    f1: float
    f2: float
    ratio_ints: tuple[int, int]
    terms: list[int]
    convergents: list[tuple[int, int]]
    resolutions_ps: list[float]
    n_window: int
    typical_aim_ps: float
    lucky_aim_ps: float
    note: str


def grid_info(f1: float, f2: float, f_trig: float, window_frac: float) -> GridInfo:
    """Continued-fraction delay grid and aiming bounds for one shooting window.

    N is the number of L2 pulses in a ±window_frac window around 1/f_trig.
    Typical peak-to-peak aiming is ~T1/D_m where D_m is the last convergent
    denominator still ≤ N (JPCA 2025 eq. 11).
    """
    n_win = max(1, int(round(2.0 * window_frac * f2 / f_trig)))
    num, den = hz_to_ints(f1, f2)
    terms = continued_fraction(num, den)
    conv = convergents(terms)
    t1_ps = PS / f1
    res = [t1_ps / d for _, d in conv]
    d_list = [d for _, d in conv]
    m = 0
    for i, d in enumerate(d_list):
        if d <= n_win:
            m = i
    d_m = d_list[m]
    d_next = d_list[m + 1] if m + 1 < len(d_list) else d_m
    typical = t1_ps / d_m
    lucky = t1_ps / d_next
    last_d = d_list[-1]
    if last_d == d_m and typical > 20.0:
        note = (
            "Ratio reduces to %d/%d: delays repeat on a ~%.1f ps grid. "
            "A 20 ps target is not available (nearest is 0 or that grid)."
            % (num, den, typical)
        )
    elif d_next <= n_win * 1.05:
        note = "Window covers the next convergent - aiming can reach ~%.2f ps." % lucky
    else:
        note = (
            "Window sits between D_m=%d and D_{m+1}=%d. Typical aiming ~%.2f ps, "
            "lucky ~%.2f ps." % (d_m, d_next, typical, lucky)
        )
    return GridInfo(
        f1=f1,
        f2=f2,
        ratio_ints=(num, den),
        terms=terms,
        convergents=conv,
        resolutions_ps=res,
        n_window=n_win,
        typical_aim_ps=typical,
        lucky_aim_ps=lucky,
        note=note,
    )


# ---------------------------------------------------------------------------
# Sawtooth / TDC measurement
# ---------------------------------------------------------------------------


def fractional_delay_s(t2: np.ndarray, f1: float) -> np.ndarray:
    """Delay of each L2 time vs the previous L1 pulse, in [0, T1)."""
    t1 = 1.0 / f1
    return np.mod(t2, t1)


def unwrap_period(x: np.ndarray, period: float) -> np.ndarray:
    """Unwrap a signal that lives in [0, period)."""
    if x.size == 0:
        return x.copy()
    out = np.empty_like(x, dtype=float)
    out[0] = float(x[0])
    offset = 0.0
    half = 0.5 * period
    prev = float(x[0])
    for i in range(1, x.size):
        xi = float(x[i])
        d = xi - prev
        if d < -half:
            offset += period
        elif d > half:
            offset -= period
        out[i] = xi + offset
        prev = xi
    return out


@dataclass(frozen=True)
class TdcEstimate:
    f1: float
    f2: float
    phi: float
    sigma_fit_s: float
    n_samples: int


def estimate_clocks(
    f1: float,
    f2: float,
    phi: float,
    sigma_tdc_s: float,
    n_packet: int,
    f_tdc: float,
    rng: np.random.Generator,
) -> TdcEstimate:
    """Fit f1, f2, phi from a noisy ~10 MHz TDC packet ending at t=0.

    Pulse times are known to the TDC (coarse + fine). Frequency comes from a
    linear fit of edge times vs pulse index; phase from the unwrapped
    start–stop sawtooth at the last sample. This is the paper's 'average a
    packet, then predict' model, not a full THS788 RTL.
    """
    n_packet = max(8, int(n_packet))
    div2 = max(1, int(round(f2 / f_tdc)))
    div1 = max(1, int(round(f1 / f_tdc)))
    m = np.arange(-n_packet * div2, 0, div2, dtype=np.int64)
    n = np.arange(-n_packet * div1, 0, div1, dtype=np.int64)
    if m.size < 2 or n.size < 2:
        return TdcEstimate(f1, f2, phi, sigma_tdc_s, 0)

    t2 = phi + m.astype(float) / f2
    t1 = n.astype(float) / f1
    t2m = t2 + rng.normal(0.0, sigma_tdc_s, size=t2.shape)
    t1m = t1 + rng.normal(0.0, sigma_tdc_s, size=t1.shape)
    f2_hat = 1.0 / float(np.polyfit(m.astype(float), t2m, 1)[0])
    f1_hat = 1.0 / float(np.polyfit(n.astype(float), t1m, 1)[0])

    return TdcEstimate(
        f1=f1_hat,
        f2=f2_hat,
        phi=0.0,
        sigma_fit_s=sigma_tdc_s / math.sqrt(n_packet),
        n_samples=int(m.size),
    )


def sawtooth_trace(
    f1: float, f2: float, phi: float, n_pulses: int = 400
) -> tuple[np.ndarray, np.ndarray]:
    """First n_pulses of the L2-vs-previous-L1 delay sawtooth (seconds)."""
    m = np.arange(n_pulses, dtype=float)
    t2 = phi + m / f2
    return m, fractional_delay_s(t2, f1)


# ---------------------------------------------------------------------------
# Pulse picker
# ---------------------------------------------------------------------------


def window_bounds(n_prev: int, f: float, t_trig: float, window_frac: float) -> tuple[int, int]:
    lo = n_prev + int(math.ceil(f * t_trig * (1.0 - window_frac) - 1e-9))
    hi = n_prev + int(math.floor(f * t_trig * (1.0 + window_frac) + 1e-9))
    if hi < lo:
        center = n_prev + int(round(f * t_trig))
        lo = hi = center
    return lo, hi


def pick_pair(
    n_prev: int,
    m_prev: int,
    f1: float,
    f2: float,
    phi: float,
    target_s: float,
    t_trig: float,
    window_frac: float,
) -> tuple[int, int, float]:
    """Choose (n, m) in both period windows closest to target delay t_m - t_n."""
    n_lo, n_hi = window_bounds(n_prev, f1, t_trig, window_frac)
    m_lo, m_hi = window_bounds(m_prev, f2, t_trig, window_frac)
    n = np.arange(n_lo, n_hi + 1, dtype=np.int64)
    t1 = n.astype(float) / f1
    m = np.rint((t1 + target_s - phi) * f2).astype(np.int64)
    valid = (m >= m_lo) & (m <= m_hi)
    if not np.any(valid):
        n_c = int(n[len(n) // 2])
        m_ideal = int(round((n_c / f1 + target_s - phi) * f2))
        m_c = min(max(m_ideal, m_lo), m_hi)
        delay = phi + m_c / f2 - n_c / f1
        return n_c, int(m_c), float(delay)
    delay = phi + m.astype(float) / f2 - t1
    err = np.abs(delay - target_s)
    err = np.where(valid, err, np.inf)
    i = int(np.argmin(err))
    return int(n[i]), int(m[i]), float(delay[i])


@dataclass
class Shot:
    k: int
    role: str  # "signal" | "reference"
    target_s: float
    n: int
    m: int
    delay_s: float
    error_s: float
    t1_period_s: float
    t2_period_s: float
    n_prev: int
    m_prev: int


@dataclass
class SimResult:
    cfg: "SimConfig"
    shots: list[Shot]
    grid: GridInfo
    delay_s: np.ndarray = field(repr=False)
    error_s: np.ndarray = field(repr=False)
    t1_period_s: np.ndarray = field(repr=False)
    t2_period_s: np.ndarray = field(repr=False)
    roles: list[str] = field(default_factory=list)

    @property
    def signal_mask(self) -> np.ndarray:
        return np.array([r == "signal" for r in self.roles], dtype=bool)

    def summary(self) -> dict[str, float]:
        mask = self.signal_mask
        if not np.any(mask):
            mask = np.ones(self.error_s.size, dtype=bool)
        err = self.error_s[mask]
        t1 = self.t1_period_s[mask]
        t_trig = 1.0 / self.cfg.f_trig
        return {
            "n_signal": float(np.count_nonzero(mask)),
            "rms_ps": float(np.sqrt(np.mean(err**2)) * PS) if err.size else 0.0,
            "mae_ps": float(np.mean(np.abs(err)) * PS) if err.size else 0.0,
            "p2p_ps": float((np.max(err) - np.min(err)) * PS) if err.size else 0.0,
            "max_abs_ps": float(np.max(np.abs(err)) * PS) if err.size else 0.0,
            "within_20ps": float(np.mean(np.abs(err) * PS <= 20.0)) if err.size else 0.0,
            "within_5ps": float(np.mean(np.abs(err) * PS <= 5.0)) if err.size else 0.0,
            "t1_min_ms": float(np.min(t1) * MS) if t1.size else 0.0,
            "t1_max_ms": float(np.max(t1) * MS) if t1.size else 0.0,
            "t1_span_frac": float((np.max(t1) - np.min(t1)) / t_trig) if t1.size else 0.0,
        }


@dataclass
class SimConfig:
    f1: float = 65.012345e6
    f2: float = 65.487211e6
    f_trig: float = 1e3
    window_frac: float = 0.10
    target_s: float | Sequence[float] = 20e-12
    shots: int = 400
    phi: float = 0.0
    wander_hz: float = 0.0
    use_tdc: bool = False
    sigma_tdc_s: float = 15e-12
    n_packet: int = 4000
    f_tdc: float = 10e6
    pairing: bool = False
    seed: int = 1


def _targets(cfg: SimConfig) -> np.ndarray:
    t = cfg.target_s
    if isinstance(t, (int, float)):
        return np.full(cfg.shots, float(t), dtype=float)
    arr = np.array(list(t), dtype=float)
    if arr.size == 0:
        raise ValueError("target list is empty")
    return np.resize(arr, cfg.shots)


def run_sim(cfg: SimConfig) -> SimResult:
    rng = np.random.default_rng(cfg.seed)
    f1, f2, phi = float(cfg.f1), float(cfg.f2), float(cfg.phi)
    t_trig = 1.0 / cfg.f_trig
    targets = _targets(cfg)
    n_prev = 0
    m_prev = 0
    last_dn = None
    last_dm = None
    shots: list[Shot] = []

    for k in range(cfg.shots):
        if cfg.wander_hz:
            f1 = max(1.0, f1 + rng.normal(0.0, cfg.wander_hz))
            f2 = max(1.0, f2 + rng.normal(0.0, cfg.wander_hz))

        role = "signal"
        if cfg.pairing and (k % 2 == 1) and last_dn is not None:
            role = "reference"
            n = n_prev + last_dn
            m = m_prev + last_dm
            delay = phi + m / f2 - n / f1
            target = targets[k - 1]
        else:
            if cfg.use_tdc and cfg.sigma_tdc_s > 0.0:
                est = estimate_clocks(
                    f1, f2, phi, cfg.sigma_tdc_s, cfg.n_packet, cfg.f_tdc, rng
                )
                delay_prev = phi + m_prev / f2 - n_prev / f1
                delay_est = delay_prev + float(rng.normal(0.0, est.sigma_fit_s))
                phi_hat = delay_est - m_prev / est.f2 + n_prev / est.f1
                n, m, _pred = pick_pair(
                    n_prev,
                    m_prev,
                    est.f1,
                    est.f2,
                    phi_hat,
                    targets[k],
                    t_trig,
                    cfg.window_frac,
                )
                delay = phi + m / f2 - n / f1
            else:
                n, m, delay = pick_pair(
                    n_prev, m_prev, f1, f2, phi, targets[k], t_trig, cfg.window_frac
                )
            target = targets[k]
            last_dn = n - n_prev
            last_dm = m - m_prev

        t1p = (n - n_prev) / f1
        t2p = (m - m_prev) / f2
        shots.append(
            Shot(
                k=k,
                role=role,
                target_s=float(target),
                n=n,
                m=m,
                delay_s=float(delay),
                error_s=float(delay - target),
                t1_period_s=float(t1p),
                t2_period_s=float(t2p),
                n_prev=n_prev,
                m_prev=m_prev,
            )
        )
        n_prev, m_prev = n, m

    delay = np.array([s.delay_s for s in shots])
    error = np.array([s.error_s for s in shots])
    t1p = np.array([s.t1_period_s for s in shots])
    t2p = np.array([s.t2_period_s for s in shots])
    return SimResult(
        cfg=cfg,
        shots=shots,
        grid=grid_info(cfg.f1, cfg.f2, cfg.f_trig, cfg.window_frac),
        delay_s=delay,
        error_s=error,
        t1_period_s=t1p,
        t2_period_s=t2p,
        roles=[s.role for s in shots],
    )


PRESETS: dict[str, dict] = {
    "Free-run ~65 / 65.5 (incommensurate)": {
        "f1": 65.012345e6,
        "f2": 65.487211e6,
        "target_s": 20e-12,
        "window_frac": 0.10,
        "note": "Realistic free-run near the example pair — fine delay grid.",
    },
    "Exact 65.0 / 65.5 (130/131 trap)": {
        "f1": 65.0e6,
        "f2": 65.5e6,
        "target_s": 20e-12,
        "window_frac": 0.10,
        "note": "Commensurate 130/131 — ~117 ps grid. 20 ps is not available.",
    },
    "Paper #2 fiber / Vitara": {
        "f1": 29_981_872.0,
        "f2": 80_108_101.0,
        "target_s": 0.0,
        "window_frac": 0.006,
        "note": "JPCA 2025 Case #2, paper window ±0.6%.",
    },
    "Paper #3 two Ti:Sa": {
        "f1": 79_825_000.0,
        "f2": 80_108_124.0,
        "target_s": 20e-12,
        "window_frac": 0.006,
        "note": "JPCA 2025 Case #3 (Mai Tai / Vitara-S).",
    },
    "65 / 80 MHz": {
        "f1": 65.0e6,
        "f2": 80.0e6,
        "target_s": 20e-12,
        "window_frac": 0.10,
        "note": "Exact 13/16 — coarse grid. Detune for a useful pair.",
    },
}


def format_summary(res: SimResult) -> str:
    s = res.summary()
    g = res.grid
    return "\n".join(
        [
            "shots %d  signal %d  RMS %.3f ps  MAE %.3f ps  p2p %.3f ps  |err|max %.3f ps"
            % (
                len(res.shots),
                int(s["n_signal"]),
                s["rms_ps"],
                s["mae_ps"],
                s["p2p_ps"],
                s["max_abs_ps"],
            ),
            "within 20 ps: %4.1f%%    within 5 ps: %4.1f%%    T1 span %.3f-%.3f ms (%.1f%% of 1/f_trig)"
            % (
                100.0 * s["within_20ps"],
                100.0 * s["within_5ps"],
                s["t1_min_ms"],
                s["t1_max_ms"],
                100.0 * s["t1_span_frac"],
            ),
            "f1/f2 = %d/%d   window N=%d   typical aim ~%.2f ps   lucky ~%.2f ps"
            % (g.ratio_ints[0], g.ratio_ints[1], g.n_window, g.typical_aim_ps, g.lucky_aim_ps),
            g.note,
        ]
    )


def parse_target_ps(text: str) -> float | list[float]:
    """'20' or '0, 20, 1000' (picoseconds)."""
    parts = [p.strip() for p in str(text).replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("empty target")
    vals = [float(p) * 1e-12 for p in parts]
    return vals[0] if len(vals) == 1 else vals


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="kHz-ADASOPS picker simulator")
    p.add_argument("--f1", type=float, default=65.012345e6)
    p.add_argument("--f2", type=float, default=65.487211e6)
    p.add_argument("--f-trig", type=float, default=1e3)
    p.add_argument("--window", type=float, default=0.10, help="± fraction of 1/f_trig")
    p.add_argument("--target-ps", type=str, default="20")
    p.add_argument("--shots", type=int, default=400)
    p.add_argument("--tdc-ps", type=float, default=0.0, help=">0 enables noisy TDC estimate")
    p.add_argument("--packet", type=int, default=4000)
    p.add_argument("--wander-hz", type=float, default=0.0)
    p.add_argument("--pairing", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args(argv)
    cfg = SimConfig(
        f1=args.f1,
        f2=args.f2,
        f_trig=args.f_trig,
        window_frac=args.window,
        target_s=parse_target_ps(args.target_ps),
        shots=args.shots,
        use_tdc=args.tdc_ps > 0.0,
        sigma_tdc_s=args.tdc_ps * 1e-12,
        n_packet=args.packet,
        wander_hz=args.wander_hz,
        pairing=args.pairing,
        seed=args.seed,
    )
    res = run_sim(cfg)
    print(format_summary(res))
    print("convergents:")
    for (n, d), rps in zip(res.grid.convergents, res.grid.resolutions_ps):
        print("  %d/%d   T1/D = %.4g ps" % (n, d, rps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
