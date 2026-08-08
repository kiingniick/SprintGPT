"""Rasterize the Paceloop logo (static/icon.svg) into PNG app icons.

iOS "Add to Home Screen" does not support SVG apple-touch-icons, so we need
real PNGs for the PWA to look like an app on iPhones. This redraws the same
mark (gradient rounded square + dark "S" + dashed track) with Pillow so we
don't need an SVG rasterizer.

Run:  python tools/make_icons.py
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.normpath(os.path.join(HERE, "..", "sprintgpt", "static"))

C0 = (74, 222, 128)   # #4ade80
C1 = (34, 211, 238)   # #22d3ee
DARK = (11, 15, 23)   # #0b0f17
INK = (6, 35, 26)     # #06231a
N = 1024              # render big, downscale for crispness


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = (
                round(C0[0] + (C1[0] - C0[0]) * t),
                round(C0[1] + (C1[1] - C0[1]) * t),
                round(C0[2] + (C1[2] - C0[2]) * t),
            )
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _draw_s(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    f = _font(int(N * 0.66))
    d.text((N / 2, N / 2 + int(N * 0.02)), "P", font=f, fill=INK, anchor="mm")


def _draw_track(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    r = int(N * 196 / 512)
    cx = cy = N / 2
    w = max(4, int(N * 14 / 512))
    box = [cx - r, cy - r, cx + r, cy + r]
    dash, gap = 22, 18
    a = 0.0
    while a < 360:
        d.arc(box, a, min(a + dash, 360), fill=(*INK, 70), width=w)
        a += dash + gap


def _framed() -> Image.Image:
    """Matches icon.svg: dark backing + inset gradient panel (opaque, full-bleed)."""
    base = Image.new("RGBA", (N, N), (*DARK, 255))
    inset = int(N * 40 / 512)
    panel_r = int(N * 92 / 512)
    grad = _gradient(N).convert("RGBA")
    panel = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    pm = _rounded_mask(N, panel_r)
    pm2 = Image.new("L", (N, N), 0)
    ImageDraw.Draw(pm2).rounded_rectangle(
        [inset, inset, N - 1 - inset, N - 1 - inset], radius=panel_r, fill=255
    )
    panel.paste(grad, (0, 0), pm2)
    out = Image.alpha_composite(base, panel)
    _draw_track(out)
    _draw_s(out)
    return out


def _rounded_any(radius_frac: float, transparent: bool) -> Image.Image:
    grad = _gradient(N).convert("RGBA")
    out = Image.new("RGBA", (N, N), (0, 0, 0, 0) if transparent else (*DARK, 255))
    r = int(N * radius_frac)
    m = _rounded_mask(N, r) if transparent else Image.new("L", (N, N), 255)
    out.paste(grad, (0, 0), m)
    _draw_track(out)
    _draw_s(out)
    return out


def _save(img: Image.Image, name: str, size: int, rgb: bool = False) -> None:
    im = img.resize((size, size), Image.LANCZOS)
    if rgb:
        bg = Image.new("RGB", im.size, DARK)
        bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = bg
    path = os.path.join(STATIC, name)
    im.save(path)
    print("wrote", path)


def main() -> None:
    os.makedirs(STATIC, exist_ok=True)
    framed = _framed()
    # iOS home-screen icon: must be opaque PNG; iOS applies its own rounding.
    _save(framed, "apple-touch-icon.png", 180, rgb=True)
    # App Store / TestFlight marketing icon: 1024x1024, opaque, no alpha.
    _save(framed, "icon-1024.png", 1024, rgb=True)
    # PWA / Android icons.
    any_icon = _rounded_any(112 / 512, transparent=True)
    _save(any_icon, "icon-192.png", 192)
    _save(any_icon, "icon-512.png", 512)
    # Maskable: full-bleed, platform masks it.
    _save(_rounded_any(0.0, transparent=False), "icon-maskable-512.png", 512)


if __name__ == "__main__":
    main()
