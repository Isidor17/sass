"""Génère les textes animés au format ASS (rendus par libass dans ffmpeg).

Zones de sécurité 9:16 : on évite le haut (onglets TikTok/Reels), le bas (légende,
musique) et la colonne de droite (boutons like/commentaire/partage).
"""

from __future__ import annotations

from .plan import Caption, EditPlan
from .styles import Style

W, H = 1080, 1920
FONT = "Inter Display Black"
FONT_CLASSIC = "Inter Display SemiBold"


def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str, upper: bool = True) -> str:
    t = text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()
    return t.upper() if upper else t


def _accent_last_word(text: str, accent: str) -> str:
    words = text.split(" ")
    if len(words) < 2:
        return text
    bgr = f"&H{accent[4:6]}{accent[2:4]}{accent[0:2]}&".upper()
    return " ".join(words[:-1]) + " {\\c" + bgr + "}" + words[-1]


POP = "\\fscx70\\fscy70\\alpha&HFF&\\t(0,170,\\fscx106\\fscy106\\alpha&H00&)\\t(170,260,\\fscx100\\fscy100)"


def build_ass(plan: EditPlan, style: Style) -> str:
    white = _ass_color(style.text)
    black = _ass_color("000000")
    shadow = _ass_color("000000", 0x70)
    accent = _ass_color(style.accent)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{FONT},118,{white},{white},{black},{shadow},0,1,0,0,100,100,-1,0,1,0,5,5,90,90,0,1
Style: Label,{FONT},86,{white},{white},{black},{shadow},0,1,0,0,100,100,-1,0,1,0,4,1,80,220,0,1
Style: Sub,{FONT},48,{black},{black},{accent},{shadow},0,1,0,0,100,100,1,0,3,14,0,7,80,220,0,1
Style: Counter,{FONT},44,{accent},{accent},{black},{shadow},0,1,0,0,100,100,2,0,1,0,3,9,80,80,0,1
Style: Classic,{FONT_CLASSIC},60,{white},{white},{black},{_ass_color("000000", 0x90)},0,0,0,0,100,100,0,0,1,0,2,5,120,120,0,1
Style: Cta,{FONT},78,{white},{white},{black},{shadow},0,1,0,0,100,100,-1,0,1,0,5,5,110,110,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []

    def ev(c: Caption, style_name: str, text: str, layer: int = 0) -> None:
        lines.append(f"Dialogue: {layer},{_ts(c.start)},{_ts(c.end)},{style_name},,0,0,0,,{text}")

    classic = style.caption == "classic"
    for c in plan.captions:
        text = _clean(c.text, upper=style.caption_upper or not classic)
        if not text:
            continue
        if classic and c.kind in ("hook", "cta"):
            # Titre sobre façon texte natif Instagram : petit, centré, simple fondu.
            size = "\\fs70" if style.caption_upper else ""
            ev(c, "Classic", "{\\an5\\pos(540,1000)\\fad(150,250)" + size + "}" + text)
        elif c.kind == "hook":
            ev(c, "Hook", "{\\an5\\pos(540,780)\\fad(0,140)" + POP + "}" + _accent_last_word(text, style.accent))
        elif c.kind == "cta":
            ev(c, "Cta", "{\\an5\\pos(540,900)\\fad(0,200)" + POP + "}" + _accent_last_word(text, style.accent))
        elif c.kind == "label":
            y = 1360
            ev(c, "Label", "{\\an1\\fad(120,120)\\move(30," + str(y) + ",80," + str(y) + ",0,220)}" + text, 1)
            sub = _clean(c.sub)
            if sub:
                ev(c, "Sub", "{\\an7\\fad(160,120)\\move(30," + str(y + 26) + ",94," + str(y + 26) + ",60,280)}" + sub, 1)
            if c.counter:
                ev(c, "Counter", "{\\an9\\pos(1000,250)\\fad(120,120)}" + c.counter, 1)
    return header + "\n".join(lines) + "\n"
