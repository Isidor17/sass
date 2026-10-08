"""Montage en ligne de commande.

Exemple :
    python -m reps.cli seance/*.mp4 \
        -e "Développé couché | 4x8 | 80kg" -e "Dips lestés | 3x10 | +20kg" \
        --hook "Séance pecs" --cta "Enregistre pour ta prochaine séance" -o pecs.mp4
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from .media import FFmpegMissing
from .pipeline import analyze_sources, make_video
from .plan import parse_exercise
from .styles import STYLES


def _bar(label: str):
    def show(x: float) -> None:
        n = int(x * 30)
        sys.stderr.write(f"\r{label} [{'#' * n}{'.' * (30 - n)}] {x * 100:5.1f}%")
        if x >= 1:
            sys.stderr.write("\n")
        sys.stderr.flush()
    return show


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reps", description="Monte automatiquement une vidéo de séance en 9:16.")
    p.add_argument("rushes", nargs="+", help="Fichiers vidéo de la séance, dans l'ordre chronologique")
    p.add_argument("-e", "--exercise", action="append", default=[],
                   help='Exercice, dans l\'ordre : "Nom | 4x8 | 80kg" (répéter l\'option)')
    p.add_argument("-o", "--output", default="montage.mp4")
    p.add_argument("--hook", default="", help="Texte d'accroche des 2 premières secondes")
    p.add_argument("--cta", default="", help="Texte de fin (appel à l'action)")
    p.add_argument("--style", choices=sorted(STYLES), default="energique")
    p.add_argument("--duree", type=float, default=30.0, help="Durée cible en secondes (défaut 30)")
    p.add_argument("--musique", help="Fichier audio libre de droits (optionnel)")
    p.add_argument("--musique-debut", type=float, default=0.0, help="Démarrer la musique à N secondes")
    p.add_argument("--exclure", action="append", default=[], help="Identifiant de série à ignorer (ex. s0-2)")
    p.add_argument("--analyse-seule", action="store_true", help="Lister les séries détectées sans monter")
    args = p.parse_args(argv)

    for r in args.rushes:
        if not Path(r).is_file():
            p.error(f"fichier introuvable : {r}")

    try:
        analyses = analyze_sources(args.rushes, progress=_bar("Analyse"))
    except FFmpegMissing as e:
        print(e, file=sys.stderr)
        return 2

    for a in analyses:
        print(f"\n{Path(args.rushes[a.index]).name} ({a.track.info.duration:.0f} s, "
              f"{a.track.info.width}×{a.track.info.height})")
        for s in a.sets:
            reps = f", ~{s.reps_est} reps" if s.reps_est else ""
            print(f"  {s.id:>6}  {s.start:7.1f}s → {s.end:7.1f}s  ({s.duration:4.0f} s{reps})")
        if not a.sets:
            print("  aucune série détectée")
    if args.analyse_seule:
        return 0

    exercises = [parse_exercise(e) for e in args.exercise]
    with tempfile.TemporaryDirectory(prefix="reps-") as tmp:
        try:
            out, plan = make_video(
                args.rushes, analyses, exercises, args.output, tmp,
                style=args.style, hook=args.hook, cta=args.cta, target=args.duree,
                music=args.musique, music_start=args.musique_debut,
                excluded=set(args.exclure), progress=_bar("Rendu  "),
            )
        except ValueError as e:
            print(f"\n{e}", file=sys.stderr)
            return 1
    for w in plan.warnings:
        print(f"! {w}")
    print(f"\nVidéo prête : {out}  ({plan.duration:.1f} s)  — couverture : {out.with_suffix('.jpg')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
