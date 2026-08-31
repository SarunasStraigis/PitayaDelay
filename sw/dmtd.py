#!/usr/bin/env python3
"""DMTD lock-in (IF phase → wrapped delay) for the on-board server."""

from __future__ import annotations

import math
import socket
import time
from typing import Optional

import numpy as np

ADC_HZ_DEFAULT = 125_000_000.0
DAC_NYQUIST_HZ = 50_000_000.0
DELIMITER = "\r\n"


class Scpi:
    def __init__(self, host: str, port: int = 5000, timeout: float = 10.0) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((host, port))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def tx(self, msg: str) -> None:
        self._sock.sendall((msg + DELIMITER).encode("utf-8"))

    def rx(self) -> str:
        chunks: list[str] = []
        while True:
            piece = self._sock.recv(65536)
            if not piece:
                raise ConnectionError("SCPI connection closed")
            chunks.append(piece.decode("utf-8"))
            if "".join(chunks).endswith(DELIMITER):
                return "".join(chunks)[: -len(DELIMITER)]

    def query(self, msg: str) -> str:
        self.tx(msg)
        return self.rx()


def wrap_ps(delay_ps: float, ref_hz: float) -> float:
    period_ps = 1e12 / ref_hz
    return (delay_ps + 0.5 * period_ps) % period_ps - 0.5 * period_ps


def lo_and_beat(meas_hz: float, harmonic: int, demod_hz: float) -> tuple[float, float]:
    lo_hz = (meas_hz + demod_hz) / harmonic
    return lo_hz, abs(demod_hz)


def choose_dec(adc_hz: float, beat_hz: float) -> int:
    for dec in (65536, 8192, 1024, 64, 8, 1):
        nyquist = 0.5 * adc_hz / dec
        if nyquist > 5.0 * beat_hz:
            return dec
    return 1


def parse_buffer(text: str) -> np.ndarray:
    text = text.strip().strip("{}[]").replace(" ", "")
    if not text:
        return np.array([], dtype=np.float64)
    return np.fromstring(text, sep=",", dtype=np.float64)


def integer_cycle_n(n: int, beat_hz: float, sample_rate: float) -> int:
    if beat_hz <= 0 or n <= 1 or sample_rate <= 0:
        return n
    samples_per_cycle = sample_rate / beat_hz
    if samples_per_cycle <= 0:
        return n
    cycles = int(math.floor(n / samples_per_cycle))
    if cycles < 1:
        return n
    n_int = int(round(cycles * samples_per_cycle))
    return min(max(n_int, 1), n)


def hann_iq_mean(i_mix: np.ndarray, q_mix: np.ndarray) -> tuple[float, float]:
    n = i_mix.size
    if n < 4:
        return float(i_mix.mean()) if n else 0.0, float(q_mix.mean()) if n else 0.0
    w = 0.5 - 0.5 * np.cos(2.0 * math.pi * np.arange(n) / (n - 1))
    w_sum = float(w.sum())
    return float((i_mix * w).sum() / w_sum), float((q_mix * w).sum() / w_sum)


def fft_peak_hz(x: np.ndarray, sample_rate: float, lo_hz: float, hi_hz: float) -> Optional[float]:
    n = x.size
    if n < 16:
        return None
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    mag = np.abs(spec)
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    if not np.any(mask):
        return None
    i = int(np.argmax(mag[mask]))
    return float(freqs[mask][i])


def process_block(
    ch_a: np.ndarray,
    ch_b: np.ndarray,
    sample_rate: float,
    beat_hz: float,
    ref_hz: float,
    use_fft: bool,
) -> dict:
    n = min(ch_a.size, ch_b.size)
    ch_a = ch_a[:n]
    ch_b = ch_b[:n]
    nyquist = 0.5 * sample_rate

    fft_hz = fft_peak_hz(ch_a, sample_rate, 20.0, min(nyquist * 0.98, 20_000.0))
    nco_hz = beat_hz
    if use_fft:
        near = fft_peak_hz(
            ch_a,
            sample_rate,
            max(20.0, beat_hz * 0.7),
            min(nyquist * 0.98, beat_hz * 1.4 + 50.0),
        )
        peak = near if near is not None else fft_hz
        if peak is not None:
            nco_hz = peak

    t = np.arange(n, dtype=np.float64) / sample_rate
    phase = 2.0 * math.pi * nco_hz * t
    cos_ref = np.cos(phase)
    sin_ref = np.sin(phase)

    n_eff = integer_cycle_n(n, nco_hz, sample_rate)
    i_a, q_a = hann_iq_mean(ch_a[:n_eff] * cos_ref[:n_eff], ch_a[:n_eff] * sin_ref[:n_eff])
    i_b, q_b = hann_iq_mean(ch_b[:n_eff] * cos_ref[:n_eff], ch_b[:n_eff] * sin_ref[:n_eff])

    mag_a = math.hypot(i_a, q_a)
    mag_b = math.hypot(i_b, q_b)
    phi_a = math.atan2(q_a, i_a)
    phi_b = math.atan2(q_b, i_b)
    diff = math.atan2(math.sin(phi_a - phi_b), math.cos(phi_a - phi_b))
    ps_per_rad = 1e12 / (2.0 * math.pi * ref_hz)

    return {
        "beat_hz": nco_hz,
        "fft_hz": float("nan") if fft_hz is None else fft_hz,
        "diff_rad": diff,
        "diff_deg": diff * 180.0 / math.pi,
        "diff_ps": diff * ps_per_rad,
        "rms_a": float(np.sqrt(np.mean(ch_a * ch_a))),
        "rms_b": float(np.sqrt(np.mean(ch_b * ch_b))),
        "mag_a": mag_a,
        "mag_b": mag_b,
    }


def configure_acq(rp: Scpi, dec: int) -> None:
    rp.tx("ACQ:RST")
    rp.tx("ACQ:DEC %d" % dec)
    rp.tx("ACQ:DATA:Units VOLTS")
    rp.tx("ACQ:DATA:FORMAT ASCII")
    rp.tx("ACQ:SOUR1:GAIN LV")
    rp.tx("ACQ:SOUR2:GAIN LV")
    rp.tx("ACQ:AVG ON")


def configure_square_lo(rp: Scpi, lo_hz: float, volt: float, channel: int) -> None:
    rp.tx("GEN:RST")
    rp.tx("SOUR%d:FUNC SQUARE" % channel)
    rp.tx("SOUR%d:FREQ:FIX %s" % (channel, lo_hz))
    rp.tx("SOUR%d:VOLT %s" % (channel, volt))
    rp.tx("SOUR%d:VOLT:OFFS 0" % channel)
    rp.tx("SOUR%d:DCYC 50" % channel)
    rp.tx("SOUR%d:PHAS 0" % channel)
    rp.tx("OUTPUT%d:STATE ON" % channel)
    rp.tx("SOUR:TRig:INT")
    time.sleep(0.15)


def acquire_pair(rp: Scpi) -> tuple[np.ndarray, np.ndarray]:
    rp.tx("ACQ:START")
    rp.tx("ACQ:TRig NOW")

    deadline = time.time() + 15.0
    while time.time() < deadline:
        if rp.query("ACQ:TRig:STAT?").strip() == "TD":
            break
        time.sleep(0.02)
    else:
        raise TimeoutError("Timed out waiting for ACQ:TRig:STAT? TD")

    try:
        fill = rp.query("ACQ:TRig:FILL?").strip()
        if fill in ("0", "OFF", "NO"):
            fill_deadline = time.time() + 5.0
            while time.time() < fill_deadline:
                fill = rp.query("ACQ:TRig:FILL?").strip()
                if fill in ("1", "ON", "YES"):
                    break
                time.sleep(0.02)
    except (OSError, ConnectionError, TimeoutError, socket.timeout):
        pass

    a = parse_buffer(rp.query("ACQ:SOUR1:DATA?"))
    b = parse_buffer(rp.query("ACQ:SOUR2:DATA?"))
    if a.size < 64 or b.size < 64:
        raise RuntimeError("Short buffers: IN1=%d IN2=%d" % (a.size, b.size))
    return a, b
