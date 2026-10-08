"""Estimation du tempo (BPM) d'une musique pour caler les coupes sur le temps."""

from __future__ import annotations

import numpy as np

from .media import audio_mono

SR = 11025
HOP = 256


def estimate_bpm(path: str, max_seconds: float = 90.0, lo: float = 70.0, hi: float = 180.0) -> float | None:
    y = audio_mono(path, SR)[: int(max_seconds * SR)]
    if len(y) < SR * 5:
        return None
    n = len(y) // HOP
    frames = y[: n * HOP].reshape(n, HOP)
    energy = np.log1p(100 * np.sqrt((frames ** 2).mean(axis=1)))
    onset = np.maximum(0.0, np.diff(energy))  # montées d'énergie = attaques (kick, snare)
    onset -= onset.mean()
    if not np.any(onset):
        return None
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    rate = SR / HOP
    lags = np.arange(len(ac))
    with np.errstate(divide="ignore"):
        bpms = 60.0 * rate / np.maximum(lags, 1)
    valid = (bpms >= lo) & (bpms <= hi)
    if not np.any(valid):
        return None
    lag = int(lags[valid][np.argmax(ac[valid])])
    return round(60.0 * rate / lag, 1)
