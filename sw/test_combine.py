#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sw"))
import combine


def test_hybrid_nominal():
    f = 65e6
    period = 1e12 / f
    tdc = 3.1 * period
    dmtd = 0.1 * period
    h = combine.hybrid_unwrap(tdc, dmtd, f)
    assert h["n"] == 3
    assert abs(h["delay_ps"] - 3.1 * period) < 1e-6
    assert not h["unwrap_slip"]


def test_hybrid_slip():
    f = 65e6
    period = 1e12 / f
    h = combine.hybrid_unwrap(0.0, 0.4 * period, f)
    assert h["unwrap_slip"]


def test_ratio():
    assert combine.ratio_near_integer(65e6, 100e3) is True
    assert combine.ratio_near_integer(65e6, 99e3) is False


if __name__ == "__main__":
    test_hybrid_nominal()
    test_hybrid_slip()
    test_ratio()
    print("ok")
