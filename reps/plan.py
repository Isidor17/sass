"""Transforme les séries détectées + la description de la séance en plan de montage."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import numpy as np

from .motion import SetSegment, SourceAnalysis, best_window
from .styles import Style

HOOK_LEN = 2.0
MIN_CUT = 1.6
MAX_PER_EXERCISE = 14.0
MAX_CUT = 4.5


@dataclass
class Exercise:
    name: str
    detail: str = ""
    sets: int | None = None


def exercise_from_fields(name: str, sets: int | None = None, reps: str = "", load: str = "") -> Exercise:
    """Champs du formulaire -> Exercise. reps peut être « 8 » ou « 8-10 »."""
    name = name.strip()
    if not name:
        raise ValueError("Nom d'exercice vide")
    parts = []
    if sets and reps:
        parts.append(f"{sets}×{reps.strip()}")
    elif sets:
        parts.append(f"{sets} séries")
    elif reps:
        parts.append(f"{reps.strip()} reps")
    if load and load.strip():
        parts.append(load.strip())
    return Exercise(name=name, detail=" · ".join(parts), sets=sets or None)


def parse_exercise(line: str) -> Exercise:
    """« Développé couché | 4x8 | 80kg » -> Exercise(name, detail="4×8 · 80KG", sets=4)."""
    parts = [p.strip() for p in line.split("|") if p.strip()]
    if not parts:
        raise ValueError("Exercice vide")
    name = parts[0]
    extras = parts[1:]
    sets = None
    for p in extras:
        m = re.search(r"(\d+)\s*[x×]\s*\d+", p, re.I)
        if m:
            sets = int(m.group(1))
            break
    detail = " · ".join(re.sub(r"\s*[x×]\s*", "×", p, flags=re.I) for p in extras)
    return Exercise(name=name, detail=detail, sets=sets)


@dataclass
class Clip:
    source: int
    start: float  # secondes dans le rush
    src_duration: float  # durée prélevée dans le rush
    speed: float
    cx: float
    role: str  # "hook" | "exercise"
    group: int = -1

    @property
    def duration(self) -> float:
        return self.src_duration / self.speed


@dataclass
class Caption:
    kind: str  # "hook" | "label" | "cta"
    start: float
    end: float
    text: str
    sub: str = ""
    counter: str = ""


@dataclass
class EditPlan:
    clips: list[Clip]
    captions: list[Caption]
    style: str
    warnings: list[str] = field(default_factory=list)
    groups: list[list[str]] = field(default_factory=list)  # ids des séries, par exercice

    @property
    def duration(self) -> float:
        return sum(c.duration for c in self.clips)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        return d


def _group_sets(active: list[SetSegment], exercises: list[Exercise], warnings: list[str]) -> list[list[SetSegment]]:
    n = len(exercises)
    if n == 0:
        return [[s] for s in active]
    if len(active) <= n:
        if len(active) < n:
            warnings.append(
                f"{len(active)} série(s) détectée(s) pour {n} exercices : "
                f"les {n - len(active)} dernier(s) exercice(s) ne seront pas montrés."
            )
        return [[s] for s in active]

    counts = [e.sets for e in exercises]
    if all(counts) and sum(counts) == len(active):
        groups, i = [], 0
        for c in counts:
            groups.append(active[i:i + c])
            i += c
        return groups

    sources = sorted({s.source for s in active})
    if len(sources) == n:
        return [[s for s in active if s.source == src] for src in sources]

    if all(counts):
        warnings.append(
            f"Tu as indiqué {sum(counts)} séries au total, j'en détecte {len(active)}. "
            "Je regroupe par les plus longues pauses (changement d'exercice)."
        )
    # Changement d'exercice = pause plus longue (installation du matériel).
    gaps = []
    for a, b in zip(active[:-1], active[1:]):
        gaps.append(b.start - a.end if a.source == b.source else np.nan)
    gaps_arr = np.array(gaps, dtype=float)
    fill = np.nanmean(gaps_arr) if np.any(~np.isnan(gaps_arr)) else 0.0
    gaps_arr = np.where(np.isnan(gaps_arr), fill, gaps_arr)
    cut_after = sorted(np.argsort(-gaps_arr, kind="stable")[: n - 1].tolist())
    groups, i = [], 0
    for c in cut_after:
        groups.append(active[i:c + 1])
        i = c + 1
    groups.append(active[i:])
    return groups


def _quantize(length: float, bpm: float | None) -> float:
    if not bpm:
        return length
    beat = 60.0 / bpm
    beats = max(2, int(round(length / beat)))
    return beats * beat


def _score(s: SetSegment) -> float:
    return s.energy * (0.5 + s.periodicity)


def build_plan(
    analyses: list[SourceAnalysis],
    exercises: list[Exercise],
    style: Style,
    hook: str = "",
    cta: str = "",
    target: float = 30.0,
    bpm: float | None = None,
    excluded: set[str] | None = None,
) -> EditPlan:
    excluded = excluded or set()
    warnings: list[str] = []
    by_source = {a.index: a for a in analyses}
    active = [s for a in sorted(analyses, key=lambda a: a.index) for s in a.sets if s.id not in excluded]
    if not active:
        raise ValueError("Aucune série détectée (ou toutes exclues) : rien à monter.")

    groups = _group_sets(active, exercises, warnings)
    if not exercises and len(groups) > 8:
        # Sans description de séance : on garde les 8 meilleures séries, dans l'ordre.
        best = sorted(sorted(range(len(groups)), key=lambda i: -_score(groups[i][0]))[:8])
        groups = [groups[i] for i in best]

    speed = style.speed

    def make_clip(seg: SetSegment, length: float, role: str, group: int) -> Clip:
        src_len = min(length * speed, seg.duration)
        track = by_source[seg.source].track
        start = best_window(track, seg, src_len)
        return Clip(seg.source, start, round(src_len, 3), speed, seg.cx, role, group)

    clips: list[Clip] = []
    captions: list[Caption] = []

    hook_len = _quantize(HOOK_LEN, bpm)
    hero = max(active, key=_score)
    clips.append(make_clip(hero, hook_len, "hook", -1))
    if hook:
        captions.append(Caption("hook", 0.0, clips[0].duration, hook))

    per_group = float(np.clip((target - hook_len) / len(groups), 2.2, MAX_PER_EXERCISE))
    for gi, sets in enumerate(groups):
        n_cuts = int(np.clip(round(per_group / 3.2), 1, len(sets)))
        cut_len = _quantize(float(np.clip(per_group / n_cuts, MIN_CUT, MAX_CUT)), bpm)
        # Toujours la dernière série (fatigue, dernières reps), puis les plus intenses.
        picks = [sets[-1]] + sorted(sets[:-1], key=_score, reverse=True)
        picks = sorted(picks[:n_cuts], key=lambda s: (s.source, s.start))
        group_start = sum(c.duration for c in clips)
        for seg in picks:
            clips.append(make_clip(seg, cut_len, "exercise", gi))
        group_end = sum(c.duration for c in clips)
        if exercises and gi < len(exercises):
            ex = exercises[gi]
            captions.append(
                Caption("label", group_start + 0.08, group_end, ex.name, ex.detail,
                        f"{gi + 1:02d}/{min(len(groups), len(exercises)):02d}")
            )

    total = sum(c.duration for c in clips)
    if total < target - 3:
        warnings.append(
            f"Vidéo de {total:.0f} s au lieu de {target:.0f} s : pas assez de séries pour remplir "
            "(au maximum un plan par série)."
        )
    if cta:
        cta_start = max(0.0, total - 1.8)
        for c in captions:
            if c.kind == "label" and c.end > cta_start:
                c.end = max(c.start + 0.5, cta_start)
        captions.append(Caption("cta", cta_start, total, cta))
    return EditPlan(clips=clips, captions=captions, style=style.key, warnings=warnings,
                    groups=[[s.id for s in g] for g in groups])
