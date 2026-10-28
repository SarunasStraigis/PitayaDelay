#!/usr/bin/env python3
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import adasops_sim as S


def test_convergents_130_131():
    terms = S.continued_fraction(130, 131)
    conv = S.convergents(terms)
    assert conv[-1] == (130, 131)
    g = S.grid_info(65e6, 65.5e6, 1e3, 0.10)
    assert g.ratio_ints == (130, 131)
    assert abs(g.typical_aim_ps - 1e12 / 65e6 / 131) < 0.05


def test_unwrap_ramp():
    t1 = 1.0 / 65e6
    x = np.mod(np.arange(200) * (t1 * 0.37), t1)
    uw = S.unwrap_period(x, t1)
    step = np.diff(uw)
    assert np.all(step > 0)
    assert abs(float(np.mean(step)) - t1 * 0.37) < t1 * 1e-6


def test_period_clamp():
    cfg = S.SimConfig(
        f1=65.012345e6,
        f2=65.487211e6,
        window_frac=0.10,
        shots=80,
        target_s=20e-12,
        seed=2,
    )
    res = S.run_sim(cfg)
    t_trig = 1.0 / cfg.f_trig
    # First shot is measured from n=0; skip it. The rest must stay in ±10%.
    assert np.all(res.t1_period_s[1:] >= t_trig * (1.0 - cfg.window_frac) - 1e-12)
    assert np.all(res.t1_period_s[1:] <= t_trig * (1.0 + cfg.window_frac) + 1e-12)
    assert np.all(res.t2_period_s[1:] >= t_trig * (1.0 - cfg.window_frac) - 1e-12)
    assert np.all(res.t2_period_s[1:] <= t_trig * (1.0 + cfg.window_frac) + 1e-12)


def test_exact_655_cannot_hit_20ps():
    cfg = S.SimConfig(
        f1=65.0e6,
        f2=65.5e6,
        window_frac=0.10,
        shots=60,
        target_s=20e-12,
        seed=1,
    )
    res = S.run_sim(cfg)
    # Grid is ~117 ps. Closest to 20 ps is 0, so error is constantly -20 ps.
    assert abs(res.summary()["mae_ps"] - 20.0) < 0.05
    assert res.summary()["within_5ps"] == 0.0


def test_freerun_can_hit_20ps():
    cfg = S.SimConfig(
        f1=65.012345e6,
        f2=65.487211e6,
        window_frac=0.10,
        shots=80,
        target_s=20e-12,
        seed=1,
    )
    res = S.run_sim(cfg)
    assert res.summary()["max_abs_ps"] < 5.0
    assert res.summary()["within_5ps"] > 0.95


def test_pairing_repeats_elapsed():
    cfg = S.SimConfig(
        f1=65.012345e6,
        f2=65.487211e6,
        window_frac=0.10,
        shots=10,
        pairing=True,
        seed=3,
    )
    res = S.run_sim(cfg)
    for i, sh in enumerate(res.shots):
        if sh.role == "reference":
            prev = res.shots[i - 1]
            assert sh.n - sh.n_prev == prev.n - prev.n_prev
            assert sh.m - sh.m_prev == prev.m - prev.m_prev


def test_parse_targets():
    assert S.parse_target_ps("20") == 20e-12
    assert S.parse_target_ps("0, 20, 1000") == [0.0, 20e-12, 1000e-12]


if __name__ == "__main__":
    test_convergents_130_131()
    test_unwrap_ramp()
    test_period_clamp()
    test_exact_655_cannot_hit_20ps()
    test_freerun_can_hit_20ps()
    test_pairing_repeats_elapsed()
    test_parse_targets()
    print("ok")
