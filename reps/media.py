"""Accès bas niveau aux fichiers vidéo/audio via ffmpeg/ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterator

import numpy as np


class FFmpegMissing(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegMissing(
                f"'{tool}' introuvable. Installe FFmpeg (https://ffmpeg.org/download.html) "
                "et vérifie qu'il est dans le PATH."
            )


@dataclass
class VideoInfo:
    path: str
    width: int  # dimensions affichées (rotation appliquée)
    height: int
    duration: float
    fps: float

    @property
    def aspect(self) -> float:
        return self.width / self.height


def _parse_rate(rate: str) -> float:
    try:
        num, den = rate.split("/")
        return float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str) -> VideoInfo:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate:stream_tags=rotate"
            ":stream_side_data=rotation:format=duration",
            "-of", "json", path,
        ],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise ValueError(f"Fichier vidéo illisible : {path}\n{out.stderr.strip()}")
    data = json.loads(out.stdout)
    if not data.get("streams"):
        raise ValueError(f"Aucune piste vidéo dans {path}")
    st = data["streams"][0]
    w, h = int(st["width"]), int(st["height"])

    rotation = 0
    if "tags" in st and "rotate" in st["tags"]:
        rotation = int(st["tags"]["rotate"])
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    if abs(rotation) % 180 == 90:  # vidéo de téléphone tenue verticalement
        w, h = h, w

    fps = _parse_rate(st.get("avg_frame_rate", "0/0")) or _parse_rate(st.get("r_frame_rate", "0/0")) or 30.0
    duration = float(data.get("format", {}).get("duration") or 0.0)
    return VideoInfo(path=path, width=w, height=h, duration=duration, fps=fps)


def gray_frames(path: str, info: VideoInfo, fps: float, width: int) -> Iterator[np.ndarray]:
    """Décode la vidéo en petites images en niveaux de gris, à cadence réduite."""
    height = max(2, int(round(width / info.aspect / 2)) * 2)
    proc = subprocess.Popen(
        [
            "ffmpeg", "-v", "error", "-i", path, "-an",
            "-vf", f"fps={fps},scale={width}:{height}:flags=area,format=gray",
            "-f", "rawvideo", "pipe:1",
        ],
        stdout=subprocess.PIPE,
    )
    frame_size = width * height
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(frame_size)
            if len(buf) < frame_size:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width)
    finally:
        proc.stdout.close()
        proc.wait()


def audio_mono(path: str, sample_rate: int = 11025) -> np.ndarray:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"],
        capture_output=True,
    )
    if out.returncode != 0:
        raise ValueError(f"Fichier audio illisible : {path}")
    return np.frombuffer(out.stdout, dtype=np.float32)
