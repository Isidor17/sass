"""Tests de bout en bout sur une vidéo de synthèse.

Lancer : python -m unittest discover -s tests -v
La vidéo simule un trépied fixe : fond immobile, un « athlète » (rectangle) qui
fait des répétitions de 2,5 s pendant deux séries, immobile pendant le repos.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from reps.captions import build_ass
from reps.music import estimate_bpm
from reps.motion import analyze_motion, detect_sets
from reps.pipeline import analyze_sources, make_video
from reps.plan import build_plan, exercise_from_fields, parse_exercise
from reps.styles import get_style

SETS = [(4.0, 16.0), (26.0, 38.0)]
REP = 2.5


def make_synthetic(path: Path, width: int = 360, height: int = 640, duration: float = 44.0, x: int = 230) -> None:
    active = "+".join(f"between(t,{a},{b})" for a, b in SETS)
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=0x2a2a2e:s={width}x{height}:r=30:d={duration}",
            "-f", "lavfi", "-i", f"color=c=0xc89070:s=60x150:r=30:d={duration}",
            "-filter_complex", f"[0][1]overlay=x={x}:y='240+90*sin(2*PI*t/{REP})*({active})'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", str(path),
        ],
        check=True,
    )


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.vertical = cls.dir / "vertical.mp4"
        cls.landscape = cls.dir / "paysage.mp4"
        make_synthetic(cls.vertical)
        make_synthetic(cls.landscape, width=640, height=360, x=450)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_detects_sets_and_reps(self) -> None:
        sets = detect_sets(analyze_motion(str(self.vertical)))
        self.assertEqual(len(sets), 2)
        for seg, (a, b) in zip(sets, SETS):
            self.assertAlmostEqual(seg.start, a, delta=1.0)
            self.assertAlmostEqual(seg.end, b, delta=1.0)
            self.assertIsNotNone(seg.rep_period)
            self.assertAlmostEqual(seg.rep_period, REP, delta=0.4)

    def test_subject_position_in_landscape(self) -> None:
        sets = detect_sets(analyze_motion(str(self.landscape)))
        # Le sujet est centré vers x = (450 + 30) / 640 = 0,75.
        self.assertTrue(all(abs(s.cx - 0.75) < 0.08 for s in sets), [s.cx for s in sets])

    def test_plan_groups_by_declared_set_counts(self) -> None:
        analyses = analyze_sources([str(self.vertical), str(self.landscape)])
        exercises = [parse_exercise("Squat | 3x5 | 100kg"), parse_exercise("Tractions | 1x8")]
        plan = build_plan(analyses, exercises, get_style("energique"), hook="Leg day", cta="Abonne-toi", target=20)
        self.assertEqual([len(g) for g in plan.groups], [3, 1])
        self.assertEqual(plan.clips[0].role, "hook")
        labels = [c for c in plan.captions if c.kind == "label"]
        self.assertEqual([c.text for c in labels], ["Squat", "Tractions"])
        self.assertEqual(labels[0].sub, "3×5 · 100kg")

    def test_excluded_sets_are_skipped(self) -> None:
        analyses = analyze_sources([str(self.vertical)])
        plan = build_plan(analyses, [], get_style("clean"), excluded={"s0-0"})
        self.assertEqual(plan.groups, [["s0-1"]])
        with self.assertRaises(ValueError):
            build_plan(analyses, [], get_style("clean"), excluded={"s0-0", "s0-1"})

    def test_render_vertical_video(self) -> None:
        analyses = analyze_sources([str(self.vertical), str(self.landscape)])
        out = self.dir / "out" / "montage.mp4"
        path, plan = make_video(
            [str(self.vertical), str(self.landscape)], analyses,
            [exercise_from_fields("Développé couché", 2, "8", "80 kg"), exercise_from_fields("Dips", None, "10")],
            out, self.dir / "work", style="energique", hook="Séance pecs", cta="Enregistre", target=16,
        )
        meta = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
             "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout)
        video = next(s for s in meta["streams"] if s["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (1080, 1920))
        self.assertTrue(any(s["codec_type"] == "audio" for s in meta["streams"]))
        self.assertAlmostEqual(float(meta["format"]["duration"]), plan.duration, delta=0.2)
        self.assertTrue(path.with_suffix(".jpg").is_file())

    def test_bpm_estimation(self) -> None:
        click = self.dir / "click.wav"
        # Clic de 50 ms toutes les 0,5 s = 120 BPM.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='sin(2*PI*880*t)*lt(mod(t,0.5),0.05)':s=44100:d=20", str(click)], check=True)
        bpm = estimate_bpm(str(click))
        self.assertIsNotNone(bpm)
        self.assertAlmostEqual(bpm, 120, delta=3)

    def test_ass_escapes_user_text(self) -> None:
        analyses = analyze_sources([str(self.vertical)])
        plan = build_plan(analyses, [parse_exercise("Curl {biceps}\\N")], get_style("energique"), hook="a{b}c")
        ass = build_ass(plan, get_style("energique"))
        self.assertIn("CURL (BICEPS)/N", ass)
        self.assertNotIn("{b}", ass)


if __name__ == "__main__":
    unittest.main()
