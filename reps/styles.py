"""Styles de montage. Chaque style = rythme + mouvement de caméra + étalonnage + typo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    speed: float  # accélération des plans (1.0 = vitesse réelle)
    zoom: str  # "punch" (coup de zoom en fin de plan), "push" (zoom lent continu), "none"
    grade: str  # chaîne de filtres ffmpeg appliquée à chaque plan
    accent: str  # couleur d'accent, hex RRGGBB
    text: str  # couleur du texte principal, hex RRGGBB
    flash: bool  # flash blanc de 2 images entre le hook et la suite
    hook_clip: bool = True  # plan d'accroche de 2 s avant le premier exercice
    labels: bool = True  # étiquettes exercice / séries×reps / charge
    caption: str = "bold"  # "bold" (gros, majuscules, animé) ou "classic" (sobre, minuscules)
    max_cut: float = 4.5  # durée max d'un plan (s)
    max_cuts: int = 3  # plans max par exercice
    punch_every: float = 1.3  # "jumpcut" : alternance large/serré toutes les N s
    punch_scale: float = 1.3
    end_bias: float = 0.6  # 0 = début de série, 1 = privilégie fortement les dernières reps
    lead_in: float = 0.0  # secondes gardées avant la série (mise en place)
    default_target: float = 30.0


STYLES: dict[str, Style] = {
    # Mesuré sur le reel de référence « Athletic Leg Day » : un plan continu par exercice
    # (3-11 s, vitesse réelle), zooms en coupe sèche large/serré toutes les ~1,3 s,
    # couleurs naturelles, un seul petit titre en minuscules, mises en place conservées.
    "athletic": Style(
        key="athletic",
        label="Athletic",
        speed=1.0,
        zoom="jumpcut",
        grade="eq=contrast=1.04:saturation=1.04,unsharp=5:5:0.35",
        accent="FFFFFF",
        text="FFFFFF",
        flash=False,
        hook_clip=False,
        labels=False,
        caption="classic",
        max_cut=9.0,
        max_cuts=1,
        punch_every=1.3,
        punch_scale=1.3,
        lead_in=1.5,
        default_target=45.0,
    ),
    "energique": Style(
        key="energique",
        label="Énergique",
        speed=1.1,
        zoom="punch",
        grade="eq=contrast=1.14:saturation=1.18:brightness=-0.015,unsharp=5:5:0.7,vignette=PI/5",
        accent="C6FF00",
        text="FFFFFF",
        flash=True,
    ),
    "cinematique": Style(
        key="cinematique",
        label="Cinématique",
        speed=1.0,
        zoom="push",
        grade=(
            "eq=contrast=1.2:saturation=0.78:brightness=-0.03,"
            "colorbalance=rs=-0.04:bs=0.05:rh=0.05:bh=-0.03,unsharp=5:5:0.5,vignette=PI/4"
        ),
        accent="FF5A1F",
        text="F2F2F2",
        flash=False,
    ),
    "clean": Style(
        key="clean",
        label="Clean",
        speed=1.0,
        zoom="none",
        grade="eq=contrast=1.06:saturation=1.06,unsharp=5:5:0.4",
        accent="4DA3FF",
        text="FFFFFF",
        flash=False,
    ),
}

DEFAULT_STYLE = "athletic"


def get_style(key: str | None) -> Style:
    return STYLES.get(key or DEFAULT_STYLE, STYLES[DEFAULT_STYLE])
