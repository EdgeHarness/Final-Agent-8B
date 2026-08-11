"""Generate the installed-app icons from the product mark. Run once; PNGs are committed.

    python3 -m webui.make_icons

The source is static/mark.png, the same white-on-transparent art the topbar and
favicon.svg use as a mask — so the icon in the dock is the icon in the tab strip.
Do not hand-draw a substitute here; if the mark changes, this regenerates.

A favicon can be transparent and let the browser chrome supply the ground, which
is what favicon.svg does. An installed-app icon cannot: the OS paints it on a
dock, a taskbar and a launcher grid, none of which agree on a colour. So these
carry their own dark tile and light ink, matching the dark theme.

Needs Pillow, which the app itself does not. This is a build step.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
SRC = os.path.join(STATIC, "mark.png")
OUT = os.path.join(STATIC, "icons")

TILE = (13, 13, 13)        # --bg, dark theme
INK = (236, 236, 236)      # --ink, dark theme

# Fraction of the canvas the mark spans. A maskable icon may be cropped to a
# circle inscribed in the square, so its art has to sit inside that safe zone.
SPAN = {"any": 0.62, "maskable": 0.42}


def render(size, purpose="any", radius_frac=0.22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    if purpose == "maskable":
        tile = Image.new("RGBA", (size, size), TILE + (255,))   # must bleed to the edge
    else:
        tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        from PIL import ImageDraw
        ImageDraw.Draw(tile).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=int(size * radius_frac), fill=TILE + (255,))
    img.alpha_composite(tile)

    # The art is a mask: take its alpha and paint our own ink through it, the
    # same trick style.css uses for .logo and favicon.svg use for the mark.
    span = int(size * SPAN[purpose])
    mark = Image.open(SRC).convert("RGBA").resize((span, span), Image.LANCZOS)
    ink = Image.new("RGBA", (span, span), INK + (255,))
    ink.putalpha(mark.getchannel("A"))
    img.alpha_composite(ink, ((size - span) // 2, (size - span) // 2))
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
    # macOS "Add to Dock" and iOS use this; it is never masked and never given a
    # radius by the OS, so it ships square.
    p = os.path.join(OUT, "apple-touch-icon.png")
    render(180, radius_frac=0.0).save(p)
    made.append(p)
    for p in made:
        print(f"{os.path.relpath(p, HERE)}  {os.path.getsize(p) // 1024} KB")


if __name__ == "__main__":
    main()
