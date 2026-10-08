"""Rendu final : un seul appel ffmpeg (découpe, recadrage 9:16, zooms, étalonnage, textes, audio)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .captions import build_ass
from .media import VideoInfo
from .plan import Clip, EditPlan
from .styles import Style

W, H, FPS = 1080, 1920, 30
FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
TARGET_ASPECT = W / H


def _crop_filter(info: VideoInfo, cx: float) -> str:
    if info.aspect > TARGET_ASPECT + 0.01:
        # Rush plus large que 9:16 (paysage, 3:4…) : on recadre autour du sujet.
        cx = min(max(cx, 0.0), 1.0)
        return f"crop=w='trunc(ih*{W}/{H}/2)*2':h=ih:x='max(0,min(iw-ow,{cx:.4f}*iw-ow/2))':y=0"
    if info.aspect < TARGET_ASPECT - 0.01:
        return f"crop=w=iw:h='trunc(iw*{H}/{W}/2)*2':x=0:y='(ih-oh)/2'"
    return ""


def _zoom_filter(clip: Clip, style: Style, info: VideoInfo) -> str:
    d = clip.duration
    if style.zoom == "jumpcut" and clip.role == "exercise":
        if d < 2 * style.punch_every:
            return ""
        # Alternance large / serré en coupe sèche, centrée sur le sujet : simule plusieurs caméras.
        z = f"(1+{style.punch_scale - 1:.3f}*mod(floor(t/{style.punch_every:.3f}),2))"
        rx = 0.5 if info.aspect > TARGET_ASPECT + 0.01 else min(max(clip.cx, 0.2), 0.8)
        return (f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,"
                f"crop={W}:{H}:x='(iw-ow)*{rx:.3f}':y='(ih-oh)*0.55'")
    if clip.role == "hook" or style.zoom == "push":
        amount = 0.10 if clip.role == "hook" else 0.06
        z = f"(1+{amount}*t/{d:.3f})"
    elif style.zoom == "punch":
        t0 = max(0.0, d - 0.45)
        z = f"(1+0.09*min(1,max(0,(t-{t0:.3f})/0.12)))"
    else:
        return ""
    return f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,crop={W}:{H}"


def crop_warning(info: VideoInfo) -> str | None:
    if info.aspect > TARGET_ASPECT + 0.01 and info.height * TARGET_ASPECT < W * 0.9:
        return (
            f"Rush en {info.width}×{info.height} : le recadrage vertical perd en netteté. "
            "Filme en vertical (ou en 4K) pour une qualité maximale."
        )
    return None


def build_command(
    plan: EditPlan,
    style: Style,
    sources: list[str],
    infos: list[VideoInfo],
    workdir: Path,
    output: Path,
    music: str | None = None,
    music_start: float = 0.0,
    music_volume: float = 1.0,
) -> list[str]:
    total = plan.duration
    args = ["ffmpeg", "-y", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-nostats"]
    for c in plan.clips:
        args += ["-ss", f"{c.start:.3f}", "-t", f"{c.src_duration:.3f}", "-i", str(Path(sources[c.source]).resolve())]
    audio_idx = len(plan.clips)
    if music:
        args += ["-ss", f"{music_start:.3f}", "-i", str(Path(music).resolve())]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]

    chains = []
    for i, c in enumerate(plan.clips):
        f = [f"setpts=(PTS-STARTPTS)/{c.speed:.4f}", f"fps={FPS}"]
        crop = _crop_filter(infos[c.source], c.cx)
        if crop:
            f.append(crop)
        f += [f"scale={W}:{H}:flags=lanczos", "setsar=1"]
        zoom = _zoom_filter(c, style, infos[c.source])
        if zoom:
            f.append(zoom)
        f.append(style.grade)
        if style.flash and i == 1 and plan.clips[0].role == "hook":
            f.append("fade=t=in:st=0:d=0.14:color=white")
        f += [f"trim=duration={c.duration:.3f}", "setpts=PTS-STARTPTS", "format=yuv420p"]
        chains.append(f"[{i}:v]{','.join(f)}[v{i}]")

    concat_in = "".join(f"[v{i}]" for i in range(len(plan.clips)))
    chains.append(f"{concat_in}concat=n={len(plan.clips)}:v=1:a=0[cat]")
    chains.append("[cat]ass=captions.ass:fontsdir=fonts,format=yuv420p[vout]")

    if music:
        fade_out = max(0.0, total - 1.2)
        chains.append(
            f"[{audio_idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
            f"afade=t=in:d=0.25,afade=t=out:st={fade_out:.3f}:d=1.2,volume={music_volume:.2f}[aout]"
        )
    else:
        chains.append(f"[{audio_idx}:a]atrim=0:{total:.3f}[aout]")

    (workdir / "filter.txt").write_text(";\n".join(chains), encoding="utf-8")
    args += [
        "-filter_complex_script", "filter.txt",
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-level", "4.2",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(output.resolve()),
    ]
    return args


def render(
    plan: EditPlan,
    style: Style,
    sources: list[str],
    infos: list[VideoInfo],
    output: str | Path,
    workdir: str | Path,
    music: str | None = None,
    music_start: float = 0.0,
    music_volume: float = 1.0,
    progress: Callable[[float], None] | None = None,
) -> Path:
    output = Path(output)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    (workdir / "captions.ass").write_text(build_ass(plan, style), encoding="utf-8")
    fonts = workdir / "fonts"
    if not fonts.exists():
        shutil.copytree(FONTS_DIR, fonts)

    cmd = build_command(plan, style, sources, infos, workdir, output, music, music_start, music_volume)
    total_us = plan.duration * 1_000_000
    with subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        for line in proc.stdout:
            if line.startswith("out_time_us=") and progress:
                try:
                    progress(min(0.99, int(line.split("=")[1]) / total_us))
                except ValueError:
                    pass
        stderr = proc.stderr.read()
    if proc.returncode != 0:
        raise RuntimeError(f"Échec du rendu ffmpeg :\n{stderr.strip()[-2000:]}")

    cover = output.with_suffix(".jpg")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{min(0.7, plan.duration / 2):.2f}", "-i", str(output),
         "-frames:v", "1", "-q:v", "2", str(cover)],
        check=False,
    )
    if progress:
        progress(1.0)
    return output
