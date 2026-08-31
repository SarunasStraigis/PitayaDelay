"""Package / overlay version. Source of truth is the VERSION file (repo root or next to this script)."""

from __future__ import annotations

import os

FALLBACK = "0.0.0-dev"


def _first_line(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text and not text.startswith("#"):
                return text
    return ""


def read_version() -> str:
    env = os.environ.get("PITAYA_DELAY_VERSION", "").strip()
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (
        os.path.join(here, "VERSION"),
        os.path.join(here, "..", "VERSION"),
        "/root/pitaya_delay/VERSION",
    ):
        if os.path.isfile(path):
            text = _first_line(path)
            if text:
                return text
    return FALLBACK


VERSION = read_version()
