"""Generate the app icons from the brand mark. Run once; the PNGs are committed.

    python3 -m webui.make_icons

Kept as code rather than checked-in binaries alone so the icon can be re-cut when
the accent colour changes, and so nobody has to open a design tool to fix a
rounding artefact. Needs Pillow, which the launcher does not — this is a build
step, not a runtime dependency.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "static", "icons")

BG = (18, 21, 28)         # --panel
ACCENT = (91, 140, 255)   # --accent
GLOW = (91, 140, 255, 46)

# Fraction of the canvas the diamond spans. A maskable icon may be cropped to a
# circle inscribed in the square, so its mark has to sit well inside that.
SPAN = {"any": 0.56, "maskable": 0.40}


def diamond(d, cx, cy, r, fill):
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)


def render(size, purpose="any", radius_frac=0.22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if purpose == "maskable":
        d.rectangle([0, 0, size, size], fill=BG)          # must bleed to the edge
    else:
        r = int(size * radius_frac)
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    cx = cy = size / 2
    span = SPAN[purpose] * size / 2

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(
        [(cx, cy - span * 1.45), (cx + span * 1.45, cy),
         (cx, cy + span * 1.45), (cx - span * 1.45, cy)], fill=GLOW)
    img.alpha_composite(glow)

    diamond(d, cx, cy, span, ACCENT)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    made = []
    for size in (192, 512):
        p = os.path.join(OUT, f"icon-{size}.png")
        render(size).save(p)
        made.append(p)
    p = os.path.join(OUT, "icon-512-maskable.png")
    render(512, purpose="maskable").save(p)
    made.append(p)
    # macOS Safari "Add to Dock" and iOS use this one; it is never masked, but it
    # is also never given a rounded corner by the OS, so it gets its own radius.
    p = os.path.join(OUT, "apple-touch-icon.png")
    render(180, radius_frac=0.0).save(p)
    made.append(p)
    for p in made:
        print(f"{os.path.relpath(p, HERE)}  {os.path.getsize(p) // 1024} KB")


if __name__ == "__main__":
    main()
