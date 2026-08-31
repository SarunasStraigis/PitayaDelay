"""Hybrid unwrap: TDC picks the RF cycle, DMTD is the fraction inside it."""

from __future__ import annotations

from typing import Optional


def wrap_ps(delay_ps: float, f_hz: float) -> float:
    period_ps = 1e12 / float(f_hz)
    return (delay_ps + 0.5 * period_ps) % period_ps - 0.5 * period_ps


def hybrid_unwrap(tdc_ps: float, dmtd_ps: float, f_osc: float, slip_cycles: float = 0.25) -> dict:
    """n = round(dt_tdc * f_osc - frac_dmtd); delay = (n + frac) / f_osc.

    unwrap_slip is set when the TDC fractional cycle and DMTD disagree by more
    than slip_cycles (default ¼ RF cycle). With round(), |TDC − hybrid| cannot
    exceed ½ cycle; the useful check is the residual before rounding.
    """
    f = float(f_osc)
    if f <= 0:
        raise ValueError("f_osc must be positive")
    period_ps = 1e12 / f
    frac = wrap_ps(float(dmtd_ps), f) / period_ps
    resid = float(tdc_ps) / period_ps - frac
    n = int(round(resid))
    delay_ps = (n + frac) * period_ps
    resid_err = resid - n
    slip = abs(resid_err) > float(slip_cycles)
    return {
        "n": n,
        "frac": frac,
        "delay_ps": delay_ps,
        "unwrap_slip": bool(slip),
        "tdc_ps": float(tdc_ps),
        "dmtd_ps": wrap_ps(float(dmtd_ps), f),
        "period_ps": period_ps,
        "resid_err": resid_err,
    }


def ratio_near_integer(f_osc: float, f_pick: float, atol: float = 0.02) -> Optional[bool]:
    if f_osc <= 0 or f_pick <= 0:
        return None
    ratio = f_osc / f_pick
    return abs(ratio - round(ratio)) <= atol
