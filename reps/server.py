"""Interface web locale : python -m reps  ->  http://127.0.0.1:8000"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import traceback
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .media import require_ffmpeg
from .motion import SourceAnalysis, curve
from .music import estimate_bpm
from .pipeline import analyze_sources, make_video
from .plan import build_plan, exercise_from_fields
from .styles import STYLES, get_style

HOME = Path(os.environ.get("REPS_HOME", Path.home() / "Reps"))
WEB = Path(__file__).parent / "web"
FONTS = Path(__file__).parent / "assets" / "fonts"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


@dataclass
class Project:
    id: str
    dir: Path
    names: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    status: str = "analyzing"  # analyzing | ready | rendering | done | error
    progress: float = 0.0
    error: str | None = None
    analyses: list[SourceAnalysis] = field(default_factory=list)
    music: str | None = None
    music_name: str | None = None
    bpm: float | None = None
    result: dict | None = None
    renders: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


PROJECTS: dict[str, Project] = {}
app = FastAPI(title="Reps")


def _safe_name(name: str) -> str:
    base = Path(name or "fichier").name
    return re.sub(r"[^\w.\-]+", "_", base)[:120] or "fichier"


def _get(pid: str) -> Project:
    p = PROJECTS.get(pid)
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def _save(upload: UploadFile, dest: Path) -> None:
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f, length=8 * 1024 * 1024)


def _run_analysis(p: Project) -> None:
    try:
        def prog(x: float) -> None:
            p.progress = x
        p.analyses = analyze_sources(p.paths, progress=prog)
        p.status = "ready"
    except Exception as e:  # noqa: BLE001 — remonté tel quel à l'interface
        traceback.print_exc()
        p.status, p.error = "error", str(e)


@app.post("/api/projects")
def create_project(files: list[UploadFile] = File(...)) -> dict:
    require_ffmpeg()
    vids = [f for f in files if Path(f.filename or "").suffix.lower() in VIDEO_EXT]
    if not vids:
        raise HTTPException(400, "Aucun fichier vidéo reconnu (mp4, mov, m4v, mkv, webm…)")
    pid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    pdir = HOME / "projets" / pid
    (pdir / "rushes").mkdir(parents=True)
    p = Project(id=pid, dir=pdir)
    # Les téléphones nomment les fichiers dans l'ordre de tournage (IMG_0412, IMG_0413…).
    for f in sorted(vids, key=lambda f: f.filename or ""):
        dest = pdir / "rushes" / _safe_name(f.filename or "")
        _save(f, dest)
        p.names.append(f.filename or dest.name)
        p.paths.append(str(dest))
    PROJECTS[pid] = p
    threading.Thread(target=_run_analysis, args=(p,), daemon=True).start()
    return {"id": pid}


@app.get("/api/projects/{pid}")
def project_state(pid: str) -> dict:
    p = _get(pid)
    sources = []
    for a in p.analyses:
        info = a.track.info
        sources.append({
            "name": p.names[a.index],
            "duration": round(info.duration, 2),
            "width": info.width,
            "height": info.height,
            "curve": curve(a.track),
            "sets": [s.to_dict() | {"duration": round(s.duration, 2)} for s in a.sets],
        })
    return {
        "id": p.id,
        "status": p.status,
        "progress": round(p.progress, 3),
        "error": p.error,
        "sources": sources,
        "music": {"name": p.music_name, "bpm": p.bpm} if p.music else None,
        "result": p.result,
        "folder": str(p.dir),
    }


class ExerciseIn(BaseModel):
    name: str
    sets: int | None = Field(default=None, ge=1, le=20)
    reps: str = ""
    load: str = ""


class RenderIn(BaseModel):
    exercises: list[ExerciseIn] = []
    hook: str = ""
    cta: str = ""
    style: str = "energique"
    target: float = Field(default=30.0, ge=8, le=90)
    music_start: float = Field(default=0.0, ge=0)
    music_volume: float = Field(default=1.0, ge=0, le=2)
    sync_to_beat: bool = True
    excluded: list[str] = []


def _exercises(body: RenderIn):
    return [exercise_from_fields(e.name, e.sets, e.reps, e.load) for e in body.exercises if e.name.strip()]


@app.post("/api/projects/{pid}/plan")
def preview_plan(pid: str, body: RenderIn) -> dict:
    """Aperçu instantané : quelles séries vont à quel exercice, quelle durée."""
    p = _get(pid)
    if not p.analyses:
        raise HTTPException(409, "Analyse pas encore terminée")
    try:
        plan = build_plan(p.analyses, _exercises(body), get_style(body.style), body.hook, body.cta,
                          body.target, p.bpm if body.sync_to_beat else None, set(body.excluded))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"groups": plan.groups, "duration": round(plan.duration, 1), "warnings": plan.warnings,
            "clips": len(plan.clips)}


@app.post("/api/projects/{pid}/music")
def upload_music(pid: str, file: UploadFile = File(...)) -> dict:
    p = _get(pid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, "Format audio non reconnu (mp3, wav, m4a, aac, ogg, flac)")
    dest = p.dir / f"musique{ext}"
    _save(file, dest)
    p.music, p.music_name = str(dest), file.filename
    try:
        p.bpm = estimate_bpm(str(dest))
    except ValueError:
        p.music = p.music_name = p.bpm = None
        raise HTTPException(400, "Fichier audio illisible")
    return {"name": p.music_name, "bpm": p.bpm}


@app.delete("/api/projects/{pid}/music")
def delete_music(pid: str) -> dict:
    p = _get(pid)
    p.music = p.music_name = p.bpm = None
    return {"ok": True}


def _run_render(p: Project, body: RenderIn) -> None:
    try:
        p.renders += 1
        out = p.dir / f"montage-{p.renders:02d}.mp4"

        def prog(x: float) -> None:
            p.progress = x

        _, plan = make_video(
            p.paths, p.analyses, _exercises(body), out, p.dir / "tmp",
            style=body.style, hook=body.hook, cta=body.cta, target=body.target,
            music=p.music, music_start=body.music_start, music_volume=body.music_volume,
            sync_to_beat=body.sync_to_beat, excluded=set(body.excluded), progress=prog,
        )
        p.result = {
            "video": f"/api/projects/{p.id}/files/{out.name}",
            "cover": f"/api/projects/{p.id}/files/{out.with_suffix('.jpg').name}",
            "path": str(out),
            "duration": round(plan.duration, 1),
            "warnings": plan.warnings,
        }
        p.status = "done"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        p.status, p.error = "error", str(e)
    finally:
        shutil.rmtree(p.dir / "tmp", ignore_errors=True)
        p.lock.release()


@app.post("/api/projects/{pid}/render")
def start_render(pid: str, body: RenderIn) -> dict:
    p = _get(pid)
    if not p.analyses:
        raise HTTPException(409, "Analyse pas encore terminée")
    if not p.lock.acquire(blocking=False):
        raise HTTPException(409, "Un rendu est déjà en cours")
    p.status, p.progress, p.error, p.result = "rendering", 0.0, None, None
    threading.Thread(target=_run_render, args=(p, body), daemon=True).start()
    return {"ok": True}


@app.get("/api/projects/{pid}/files/{name}")
def project_file(pid: str, name: str) -> FileResponse:
    p = _get(pid)
    path = (p.dir / _safe_name(name)).resolve()
    if path.parent != p.dir.resolve() or not path.is_file():
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(path)


@app.get("/api/styles")
def styles() -> list[dict]:
    return [{"key": s.key, "label": s.label, "accent": s.accent} for s in STYLES.values()]


app.mount("/fonts", StaticFiles(directory=FONTS), name="fonts")
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def main() -> None:
    import argparse

    import uvicorn

    ap = argparse.ArgumentParser(prog="reps", description="Interface web locale de Reps")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    require_ffmpeg()
    HOME.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Reps tourne sur {url}  —  vidéos enregistrées dans {HOME / 'projets'}")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
