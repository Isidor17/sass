"""Détection des séries dans un rush filmé sur trépied.

Principe : caméra fixe => tout pixel qui change correspond à quelqu'un qui bouge.
On mesure la part de pixels qui changent entre deux images, on lisse ce signal,
puis on sépare « activité » (séries) et « calme » (repos) par un seuil d'Otsu.
Les répétitions sont un mouvement périodique : l'autocorrélation du signal
donne une estimation de la cadence et du nombre de répétitions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .media import VideoInfo, gray_frames, probe

ANALYSIS_FPS = 6.0
ANALYSIS_WIDTH = 192
PIXEL_THRESHOLD = 14  # variation de luminance (/255) considérée comme du mouvement


@dataclass
class MotionTrack:
    info: VideoInfo
    fps: float
    score: np.ndarray  # part de pixels en mouvement, par échantillon
    cx: np.ndarray  # centre horizontal du mouvement (0..1), NaN si aucun mouvement

    @property
    def times(self) -> np.ndarray:
        return np.arange(len(self.score)) / self.fps


@dataclass
class SetSegment:
    id: str
    source: int
    start: float
    end: float
    energy: float
    periodicity: float  # 0..1, régularité du mouvement (répétitions)
    rep_period: float | None  # secondes par répétition estimées
    reps_est: int | None
    cx: float  # centre horizontal du sujet (0..1)
    excluded: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceAnalysis:
    index: int
    track: MotionTrack
    sets: list[SetSegment] = field(default_factory=list)


def analyze_motion(path: str, info: VideoInfo | None = None, progress=None) -> MotionTrack:
    info = info or probe(path)
    expected = max(1, int(info.duration * ANALYSIS_FPS))
    scores: list[float] = []
    centers: list[float] = []
    prev = None
    for i, frame in enumerate(gray_frames(path, info, ANALYSIS_FPS, ANALYSIS_WIDTH)):
        f = frame.astype(np.int16)
        if prev is None:
            scores.append(0.0)
            centers.append(np.nan)
        else:
            mask = np.abs(f - prev) > PIXEL_THRESHOLD
            frac = float(mask.mean())
            scores.append(frac)
            cols = mask.sum(axis=0)
            total = cols.sum()
            centers.append(float((cols * np.arange(len(cols))).sum() / total / len(cols)) if total > 0 else np.nan)
        prev = f
        if progress and i % 30 == 0:
            progress(min(0.99, i / expected))
    return MotionTrack(info=info, fps=ANALYSIS_FPS, score=np.asarray(scores), cx=np.asarray(centers))


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1 or len(x) < n:
        return x.copy()
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def _otsu(values: np.ndarray) -> float:
    hist, edges = np.histogram(values, bins=128)
    hist = hist.astype(float)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centers) / np.maximum(w0, 1e-9)
    m1 = (np.sum(hist * centers) - np.cumsum(hist * centers)) / np.maximum(w1, 1e-9)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.argmax(between))])


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate([[False], mask, [False]])
    diff = np.diff(padded.astype(int))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    return list(zip(starts.tolist(), ends.tolist()))


def periodicity(signal: np.ndarray, fps: float, min_period: float = 0.8, max_period: float = 6.0) -> tuple[float, float | None]:
    """Pic d'autocorrélation normalisée dans la plage de cadences plausibles d'une répétition."""
    x = signal - signal.mean()
    if len(x) < fps * min_period * 3 or not np.any(x):
        return 0.0, None
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac = ac / ac[0]
    lo = int(min_period * fps)
    hi = min(int(max_period * fps), len(ac) - 1)
    if hi <= lo:
        return 0.0, None
    lag = lo + int(np.argmax(ac[lo:hi]))
    # Une répétition = deux phases de mouvement (montée + descente) : si le double
    # du pic trouvé est presque aussi corrélé, c'est lui la vraie répétition.
    if lag / fps < 1.8 and 2 * lag + 1 < len(ac) and 2 * lag <= int(max_period * fps):
        lag2 = 2 * lag - 1 + int(np.argmax(ac[2 * lag - 1:2 * lag + 2]))  # ±1 échantillon
        if ac[lag2] >= 0.75 * ac[lag]:
            lag = lag2
    return float(max(0.0, ac[lag])), lag / fps


def detect_sets(
    track: MotionTrack,
    source: int = 0,
    min_set: float = 6.0,
    merge_gap: float = 3.0,
    pad: float = 0.5,
) -> list[SetSegment]:
    fps = track.fps
    if len(track.score) < 2:
        return []
    smooth = _smooth(track.score, int(fps * 1.5))
    noise = float(np.percentile(smooth, 10))
    peak = float(np.percentile(smooth, 98))
    if peak - noise < 0.002:
        # Quasi aucun mouvement : rien à détecter.
        return []
    threshold = max(_otsu(smooth), noise + 0.15 * (peak - noise))
    mask = smooth > threshold

    runs = _runs(mask)
    merged: list[list[int]] = []
    for s, e in runs:
        if merged and (s - merged[-1][1]) / fps <= merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    duration = track.info.duration or len(track.score) / fps
    sets: list[SetSegment] = []
    for s, e in merged:
        if (e - s) / fps < min_set:
            continue
        seg = track.score[s:e]
        per, period = periodicity(_smooth(seg, 2), fps)
        cx_vals = track.cx[s:e]
        weights = seg[~np.isnan(cx_vals)]
        cx_ok = cx_vals[~np.isnan(cx_vals)]
        cx = float(np.average(cx_ok, weights=weights)) if weights.sum() > 0 else 0.5
        start = max(0.0, s / fps - pad)
        end = min(duration, e / fps + pad)
        reps = int(round((e - s) / fps / period)) if period and per > 0.25 else None
        sets.append(
            SetSegment(
                id=f"s{source}-{len(sets)}",
                source=source,
                start=round(start, 2),
                end=round(end, 2),
                energy=float(seg.mean()),
                periodicity=round(per, 3),
                rep_period=round(period, 2) if period else None,
                reps_est=reps,
                cx=round(cx, 3),
            )
        )

    # Rush court entièrement « actif » (ex. une série filmée seule) : le garder en entier.
    if not sets and duration <= 120 and peak > 0.01:
        per, period = periodicity(track.score, fps)
        sets.append(SetSegment(f"s{source}-0", source, 0.0, round(duration, 2), float(track.score.mean()),
                               round(per, 3), period, None, 0.5))
    return sets


def curve(track: MotionTrack, points: int = 600) -> list[float]:
    """Courbe de mouvement sous-échantillonnée et normalisée pour l'affichage."""
    s = _smooth(track.score, int(track.fps))
    if len(s) == 0:
        return []
    if len(s) > points:
        edges = np.linspace(0, len(s), points + 1).astype(int)
        s = np.array([s[a:b].max() for a, b in zip(edges[:-1], edges[1:])])
    peak = s.max() or 1.0
    return [round(float(v / peak), 3) for v in s]


def best_window(track: MotionTrack, seg: SetSegment, length: float, end_bias: float = 0.6) -> float:
    """Début de la meilleure fenêtre de `length` s dans la série.

    Favorise les dernières répétitions (les plus dures, les plus « dramatiques »).
    """
    if seg.duration <= length:
        return seg.start
    fps = track.fps
    a = int(seg.start * fps)
    b = int(seg.end * fps)
    n = max(1, int(length * fps))
    sig = track.score[a:b]
    if len(sig) <= n:
        return seg.start
    sums = np.convolve(sig, np.ones(n), mode="valid")
    pos = np.linspace(0, 1, len(sums))
    weighted = sums / (sums.max() or 1.0) * (1 + end_bias * pos)
    # Ne pas couper pile sur la dépose de la charge : on évite la dernière seconde.
    cutoff = max(1, len(weighted) - int(fps))
    i = int(np.argmax(weighted[:cutoff]))
    return round(seg.start + i / fps, 2)
