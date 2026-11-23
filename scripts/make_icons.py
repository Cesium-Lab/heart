#!/usr/bin/env python3
"""make_icons.py: build every favicon, app icon, and share card from the Cs mark.

    .venv/bin/python scripts/make_icons.py

Source: assets/brand/cesium-lab-mark.png (the Cesium-Lab GitHub avatar, a pixel-art "Cs").
The mark is read as a grid of pixels and redrawn as crisp squares, so it stays sharp at any size
and can be recolored. Writes to frontend/public/ (served at the site root):

    favicon.svg, favicon.ico, apple-touch-icon.png     site icon (Cs element tile)
    favicons/{planes,music,rotation,dash}.svg + .ico   section icons
                                                       (not "icons/": Apache aliases /icons/ to its own folder)
    og/{default,planes,setlister,taptempo,rotation}.png  1200x630 link-preview cards

Needs Pillow (pinned in requirements.txt). Re-run after changing the mark or the designs.
After changing icons, bump the "?v=N" on the <link rel="icon"> tags in frontend/src/pages so
browsers (which cache tab icons very hard) fetch the new ones.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets/brand/cesium-lab-mark.png"
OUT = ROOT / "frontend/public"

BG = "#14140f"  # dark, from the Minimal page
FG = "#ffc93c"  # the Cs mark: same amber as the section icons
AMBER = "#ffc93c"  # board amber
MUTED = "#8a8a82"
BLOCK = 5  # the avatar is drawn on a 5 px grid
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def mark_grid() -> list[list[bool]]:
    """The mark as a grid of on/off cells (majority vote per 5x5 block), cropped tight."""
    im = Image.open(SRC).convert("L")
    px = im.load()
    w, h = im.size
    ox, oy = 4, 1  # grid alignment that best fits the drawing
    cols, rows = (w - ox) // BLOCK, (h - oy) // BLOCK
    grid = [
        [
            sum(
                px[ox + c * BLOCK + i, oy + r * BLOCK + j] < 128
                for i in range(BLOCK)
                for j in range(BLOCK)
            )
            > BLOCK * BLOCK // 2
            for c in range(cols)
        ]
        for r in range(rows)
    ]
    on_rows = [r for r, row in enumerate(grid) if any(row)]
    on_cols = [c for c in range(cols) if any(row[c] for row in grid)]
    return [
        row[on_cols[0] : on_cols[-1] + 1] for row in grid[on_rows[0] : on_rows[-1] + 1]
    ]


GRID = mark_grid()


def mark_svg(x: float, y: float, size: float, color: str) -> str:
    """The mark as one SVG path of merged horizontal runs, fitted into a size x size box."""
    rows, cols = len(GRID), len(GRID[0])
    cell = size / max(rows, cols)
    x += (size - cols * cell) / 2
    y += (size - rows * cell) / 2
    d = []
    for r, row in enumerate(GRID):
        c = 0
        while c < cols:
            if row[c]:
                start = c
                while c < cols and row[c]:
                    c += 1
                d.append(
                    f"M{x + start * cell:.2f} {y + r * cell:.2f}h{(c - start) * cell:.2f}v{cell:.2f}h{-(c - start) * cell:.2f}z"
                )
            else:
                c += 1
    return f'<path d="{"".join(d)}" fill="{color}"/>'


def draw_mark(img: Image.Image, x: int, y: int, size: int, color: str) -> None:
    rows, cols = len(GRID), len(GRID[0])
    cell = size / max(rows, cols)
    x0 = x + (size - cols * cell) / 2
    y0 = y + (size - rows * cell) / 2
    d = ImageDraw.Draw(img)
    for r, row in enumerate(GRID):
        for c, on in enumerate(row):
            if on:
                d.rectangle(
                    [
                        x0 + c * cell,
                        y0 + r * cell,
                        x0 + (c + 1) * cell - 0.01,
                        y0 + (r + 1) * cell - 0.01,
                    ],
                    fill=color,
                )


def tile_svg(inner: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="12" fill="{BG}"/>{inner}</svg>\n'
    )


def site_icon_svg() -> str:
    # Element-style tile with the Cs mark centered.
    return tile_svg(mark_svg(10, 10, 44, FG))


# Section icons: same dark tile, a simple amber glyph.
SECTION_ICONS = {
    # plane silhouette (same shape as the map's icon)
    "planes": '<path transform="translate(6 6) scale(1.65)" d="M16 2c1.1 0 1.9 1.2 1.9 2.6V12l10.1 6v2.6l-10.1-3.1v6.4l3.1 2.4v2.2L16 27.1l-5 1.4v-2.2l3.1-2.4v-6.4L4 20.6V18l10.1-6V4.6C14.1 3.2 14.9 2 16 2z" fill="{c}"/>',
    # two beamed eighth notes, centered on the tile (spans x 12-52, y 10-54);
    # each head's right edge meets its stem's right edge
    "music": '<g fill="{c}"><ellipse cx="20" cy="48" rx="8" ry="6"/><ellipse cx="44" cy="42" rx="8" ry="6"/>'
    '<rect x="24" y="16" width="4" height="32"/><rect x="48" y="12" width="4" height="30"/>'
    '<path d="M24 16l28-6v8l-28 6z"/></g>',
    # three rotation axes
    "rotation": '<g stroke="{c}" stroke-width="5" stroke-linecap="round" fill="none">'
    '<path d="M32 34V10"/><path d="M32 34L12 48"/><path d="M32 34l20 14"/>'
    '<path d="M18 22a18 18 0 0 1 28 0" stroke-width="3" stroke-dasharray="4 4"/></g>',
    # gauge
    "dash": '<g fill="none" stroke="{c}" stroke-width="5" stroke-linecap="round">'
    '<path d="M12 44a20 20 0 0 1 40 0"/><path d="M32 44l11-13"/></g><circle cx="32" cy="44" r="4" fill="{c}"/>',
}


# Pillow versions of the same glyphs (for the .ico files), drawn on the 64-unit grid at scale s.
def paint_mark(img: Image.Image, d: ImageDraw.ImageDraw, s: int) -> None:
    draw_mark(img, 10 * s, 10 * s, 44 * s, FG)


def paint_planes(img: Image.Image, d: ImageDraw.ImageDraw, s: int) -> None:
    pts = [
        (16, 2),
        (17.9, 4.6),
        (17.9, 12),
        (28, 18),
        (28, 20.6),
        (17.9, 17.5),
        (17.9, 23.9),
        (21, 26.3),
        (21, 28.5),
        (16, 27.1),
        (11, 28.5),
        (11, 26.3),
        (14.1, 23.9),
        (14.1, 17.5),
        (4, 20.6),
        (4, 18),
        (14.1, 12),
        (14.1, 4.6),
    ]
    d.polygon([((6 + x * 1.65) * s, (6 + y * 1.65) * s) for x, y in pts], fill=AMBER)


def paint_music(img: Image.Image, d: ImageDraw.ImageDraw, s: int) -> None:
    for cx, cy in ((20, 48), (44, 42)):
        d.ellipse([(cx - 8) * s, (cy - 6) * s, (cx + 8) * s, (cy + 6) * s], fill=AMBER)
    d.rectangle([24 * s, 16 * s, 28 * s, 48 * s], fill=AMBER)
    d.rectangle([48 * s, 12 * s, 52 * s, 42 * s], fill=AMBER)
    d.polygon(
        [(24 * s, 16 * s), (52 * s, 10 * s), (52 * s, 18 * s), (24 * s, 24 * s)],
        fill=AMBER,
    )


def paint_rotation(img: Image.Image, d: ImageDraw.ImageDraw, s: int) -> None:
    for x2, y2 in ((32, 10), (12, 48), (52, 48)):
        d.line([(32 * s, 34 * s), (x2 * s, y2 * s)], fill=AMBER, width=5 * s)
        d.ellipse(
            [(x2 - 2.5) * s, (y2 - 2.5) * s, (x2 + 2.5) * s, (y2 + 2.5) * s], fill=AMBER
        )
    d.arc([14 * s, 13 * s, 50 * s, 49 * s], start=210, end=330, fill=AMBER, width=3 * s)


def paint_dash(img: Image.Image, d: ImageDraw.ImageDraw, s: int) -> None:
    d.arc([12 * s, 24 * s, 52 * s, 64 * s], start=180, end=360, fill=AMBER, width=5 * s)
    d.line([(32 * s, 44 * s), (43 * s, 31 * s)], fill=AMBER, width=5 * s)
    d.ellipse([28 * s, 40 * s, 36 * s, 48 * s], fill=AMBER)


PAINTERS = {
    "planes": paint_planes,
    "music": paint_music,
    "rotation": paint_rotation,
    "dash": paint_dash,
}

# Link-preview cards: (file, title, subtitle)
CARDS = [
    ("default", "Cesium Lab", "cesiumlab.net"),
    ("planes", "SFO Planes", "Live map + departures/arrivals board"),
    ("setlister", "Setlister", "Song library and setlist builder"),
    ("taptempo", "TapTempo", "Tap tempo, metronome, count-ins"),
    ("rotation", "Rotation Visualizer", "Quaternions, matrices, Euler angles"),
]


def card(title: str, subtitle: str) -> Image.Image:
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # Element tile on the left.
    d.rounded_rectangle([80, 135, 440, 495], radius=40, outline=MUTED, width=4)
    draw_mark(img, 130, 185, 260, FG)
    # Title and subtitle on the right.
    d.text((500, 230), title, font=ImageFont.truetype(FONT, 76), fill="#f5f3ec")
    d.text((502, 340), subtitle, font=ImageFont.truetype(FONT_REG, 36), fill=MUTED)
    d.text((502, 420), "cesiumlab.net", font=ImageFont.truetype(FONT, 32), fill=AMBER)
    return img


def main() -> None:
    (OUT / "favicons").mkdir(parents=True, exist_ok=True)
    (OUT / "og").mkdir(parents=True, exist_ok=True)

    (OUT / "favicon.svg").write_text(site_icon_svg())
    for name, glyph in SECTION_ICONS.items():
        (OUT / "favicons" / f"{name}.svg").write_text(tile_svg(glyph.format(c=AMBER)))

    # Raster versions: .ico for browsers that skip SVG icons (Safari, some Chrome cases) or ask
    # for /favicon.ico directly, and the iPhone home-screen icon (iOS needs PNG and rounds the
    # corners itself). Section pages get their own .ico so every browser shows the right icon.
    def tile_png(size: int, rounded: bool, paint) -> Image.Image:
        s = 8  # draw big on the same 64-unit grid as the SVGs, then shrink, for smooth edges
        img = Image.new("RGBA", (64 * s, 64 * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        box = [0, 0, 64 * s - 1, 64 * s - 1]
        if rounded:
            d.rounded_rectangle(box, radius=12 * s, fill=BG)
        else:
            d.rectangle(box, fill=BG)
        paint(img, d, s)
        return img.resize((size, size), Image.LANCZOS)

    def ico(path: Path, paint) -> None:
        tile_png(64, True, paint).save(
            path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]
        )

    ico(OUT / "favicon.ico", paint_mark)
    tile_png(180, False, paint_mark).convert("RGB").save(OUT / "apple-touch-icon.png")
    for name, paint in PAINTERS.items():
        ico(OUT / "favicons" / f"{name}.ico", paint)

    for name, title, subtitle in CARDS:
        card(title, subtitle).save(OUT / "og" / f"{name}.png", optimize=True)

    print(
        f"mark grid {len(GRID[0])}x{len(GRID)}; wrote favicon.svg/.ico, apple-touch-icon.png, "
        f"{len(SECTION_ICONS)} section icons, {len(CARDS)} share cards to {OUT}"
    )


if __name__ == "__main__":
    main()
