"""Orchestration : rushes -> analyse -> plan -> vidéo."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .media import require_ffmpeg
from .motion import SourceAnalysis, analyze_motion, detect_sets
from .music import estimate_bpm
from .plan import EditPlan, Exercise, build_plan
from .render import crop_warning, render
from .styles import get_style

Progress = Callable[[float], None]


def analyze_sources(paths: list[str], progress: Progress | None = None) -> list[SourceAnalysis]:
    require_ffmpeg()
    analyses = []
    for i, p in enumerate(paths):
        def sub(x: float, i=i) -> None:
            if progress:
                progress((i + x) / len(paths))

        track = analyze_motion(p, progress=sub)
        analyses.append(SourceAnalysis(index=i, track=track, sets=detect_sets(track, source=i)))
    if progress:
        progress(1.0)
    return analyses


def make_video(
    paths: list[str],
    analyses: list[SourceAnalysis],
    exercises: list[Exercise],
    output: str | Path,
    workdir: str | Path,
    style: str | None = None,
    hook: str = "",
    cta: str = "",
    target: float = 30.0,
    music: str | None = None,
    music_start: float = 0.0,
    music_volume: float = 1.0,
    sync_to_beat: bool = True,
    excluded: set[str] | None = None,
    progress: Progress | None = None,
) -> tuple[Path, EditPlan]:
    st = get_style(style)
    bpm = estimate_bpm(music) if music and sync_to_beat else None
    plan = build_plan(analyses, exercises, st, hook=hook, cta=cta, target=target, bpm=bpm, excluded=excluded)
    infos = [a.track.info for a in analyses]
    for info in infos:
        w = crop_warning(info)
        if w and w not in plan.warnings:
            plan.warnings.append(w)
    if bpm:
        plan.warnings.append(f"Tempo détecté : {bpm:g} BPM, coupes calées sur le temps.")
    out = render(plan, st, paths, infos, output, workdir, music, music_start, music_volume, progress)
    return out, plan
