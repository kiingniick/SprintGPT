"""Account color themes.

Each theme is a full palette of CSS custom properties. The web app injects the
selected theme's variables into every page so the whole UI recolors instantly,
and the choice is stored on the user's account so it follows them everywhere.
"""
from __future__ import annotations

# A curated set of polished presets. `ink` is the text color used on top of the
# accent (buttons, brand mark), and `glow` tints the ambient background gradient.
THEMES: dict[str, dict] = {
    "emerald": {
        "name": "Emerald", "dark": True,
        "accent": "#34d399", "accent2": "#22d3ee", "ink": "#04231b",
        "bg": "#0b0f17", "bg_soft": "#131a26", "card": "#161d2b", "card2": "#1c2536",
        "border": "#26314a", "text": "#e7ecf5", "muted": "#93a0b8", "glow": "#16233b",
    },
    "ocean": {
        "name": "Ocean", "dark": True,
        "accent": "#38bdf8", "accent2": "#818cf8", "ink": "#04121f",
        "bg": "#0a0f1c", "bg_soft": "#111a2e", "card": "#141d33", "card2": "#19233d",
        "border": "#26324f", "text": "#e8eefb", "muted": "#94a3c4", "glow": "#12294d",
    },
    "violet": {
        "name": "Violet", "dark": True,
        "accent": "#a78bfa", "accent2": "#e879f9", "ink": "#1a0f2e",
        "bg": "#0e0b18", "bg_soft": "#171326", "card": "#1a1530", "card2": "#221b3d",
        "border": "#332a52", "text": "#efeaf9", "muted": "#a99fc4", "glow": "#2a1a4d",
    },
    "sunset": {
        "name": "Sunset", "dark": True,
        "accent": "#fb923c", "accent2": "#f472b6", "ink": "#2a1300",
        "bg": "#140f13", "bg_soft": "#211820", "card": "#241a22", "card2": "#2d2029",
        "border": "#3d2c38", "text": "#f6ecf0", "muted": "#c1a9b6", "glow": "#3a1e2e",
    },
    "rose": {
        "name": "Rose", "dark": True,
        "accent": "#fb7185", "accent2": "#fda4af", "ink": "#2a0010",
        "bg": "#140c10", "bg_soft": "#21151a", "card": "#24171d", "card2": "#2d1d24",
        "border": "#3f2a33", "text": "#f8ecef", "muted": "#c6a7b0", "glow": "#3a1620",
    },
    "midnight": {
        "name": "Midnight", "dark": True,
        "accent": "#60a5fa", "accent2": "#a5b4fc", "ink": "#05101f",
        "bg": "#080a0f", "bg_soft": "#10141d", "card": "#131722", "card2": "#181d2a",
        "border": "#232a3a", "text": "#e6eaf2", "muted": "#8b95ab", "glow": "#131b2e",
    },
    "daylight": {
        "name": "Daylight", "dark": False,
        "accent": "#059669", "accent2": "#0891b2", "ink": "#ffffff",
        "bg": "#eef2f9", "bg_soft": "#ffffff", "card": "#ffffff", "card2": "#f6f8fc",
        "border": "#dbe2ee", "text": "#0f1a2b", "muted": "#5b6675", "glow": "#dbe6f7",
    },
}

DEFAULT_THEME = "emerald"

# CSS custom-property name for each palette key.
_VAR_MAP = {
    "accent": "--accent", "accent2": "--accent-2", "ink": "--accent-ink",
    "bg": "--bg", "bg_soft": "--bg-soft", "card": "--card", "card2": "--card-2",
    "border": "--border", "text": "--text", "muted": "--muted", "glow": "--glow",
}


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except (ValueError, IndexError):
        return (52, 211, 153)


def ink_for(hex_color: str) -> str:
    """Pick readable text (near-black or white) for text placed on `hex_color`."""
    r, g, b = _hex_to_rgb(hex_color)
    # Perceived luminance (sRGB approximation).
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#0a0f17" if luminance > 0.6 else "#ffffff"


def _sanitize_hex(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    v = value.strip()
    if not v.startswith("#"):
        v = "#" + v
    body = v[1:]
    if len(body) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in body):
        return v.lower()
    return fallback


def resolve_palette(theme: str | None, accent: str | None, accent2: str | None) -> dict:
    """Return the full palette dict for a user's stored theme choice.

    `theme == "custom"` blends the user's chosen accents onto the Emerald dark
    base, deriving a readable ink color automatically.
    """
    if theme == "custom":
        base = dict(THEMES[DEFAULT_THEME])
        acc = _sanitize_hex(accent, base["accent"])
        acc2 = _sanitize_hex(accent2, base["accent2"])
        base.update(accent=acc, accent2=acc2, ink=ink_for(acc), glow=acc + "33")
        base["name"] = "Custom"
        return base
    return THEMES.get(theme or DEFAULT_THEME, THEMES[DEFAULT_THEME])


def palette_to_css(palette: dict) -> str:
    """Serialize a palette into a `:root` declaration body."""
    return "".join(f"{css}:{palette[key]};" for key, css in _VAR_MAP.items() if key in palette)
