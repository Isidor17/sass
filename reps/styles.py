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


STYLES: dict[str, Style] = {
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

DEFAULT_STYLE = "energique"


def get_style(key: str | None) -> Style:
    return STYLES.get(key or DEFAULT_STYLE, STYLES[DEFAULT_STYLE])
