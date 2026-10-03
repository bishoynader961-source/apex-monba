"""Render Pharmacy Suite logos to PNG/ICO using Pillow.

SVG source: release/assets/logo.svg (512x512) and logo_with_text.svg (512x620).
Rendering is done by Pillow drawing primitives that exactly reproduce the SVG:
- rounded white-ish background rect
- vertical indigo pill (the cross's vertical bar)
- horizontal emerald pill (the cross's horizontal bar)
- white center circle
- (text variant only) "Pharmacy" bold indigo + "Suite" green wordmark

Fonts: we try to load a bold sans variant for "Pharmacy"; fall back to
Pillow's default if none is available (text still renders, just not bold).

Outputs:
  logo_512.png            512x512  icon only
  logo_with_text_512.png  512x620  icon + wordmark
  logo_32.png             32x32   favicon
  logo_256.png            256x256 installer icon
  logo.ico                multi-size ICO 16/32/48/256
"""
from __future__ import annotations

import os
import io
from PIL import Image, ImageDraw, ImageFont

ASSETS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
OUT_DIR = ASSETS  # same dir as SVGs

# ---- palette (matches SVG exactly) ----
BG      = (0xEE, 0xF2, 0xFF, 255)     # #EEF2FF
INDIGO  = (0x4F, 0x46, 0xE5, 255)     # #4F46E5
EMERALD = (0x10, 0xB9, 0x81, 232)     # #10B981 @ 0.95 alpha
WHITE   = (255, 255, 255, 255)

SVG_W, SVG_H = 512, 512
TEXT_H = 620

# cross geometry (from SVG)
V_X, V_Y, V_W, V_H = 216, 106, 80, 300
H_X, H_Y, H_W, H_H = 106, 216, 300, 80
CX, CY, CR = 256, 256, 26

RADIUS = 115  # background rx
CROSS_RX = 40

# ---------------------------------------------------------------------------
def try_load_font(bold: bool, size: int):
    """Return a truetype font of ~size px if available, else default."""
    candidates = []
    if bold:
        candidates += [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\tahomabd.ttf",
            r"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates += [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
            r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    # also probe the system fonts dir via PIL's default search path
    for cand in candidates:
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_icon(d, w, h, center_text: bool, font_bold, font_reg):
    """Draw the 512x512 icon content scaled into a w x h canvas."""
    scale = w / SVG_W  # assume square icon area

    # background rounded rect
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(RADIUS * scale), fill=BG)

    # vertical pill
    d.rounded_rectangle(
        [int(V_X * scale), int(V_Y * scale),
         int((V_X + V_W) * scale) - 1, int((V_Y + V_H) * scale) - 1],
        radius=int(CROSS_RX * scale), fill=INDIGO,
    )
    # horizontal pill
    d.rounded_rectangle(
        [int(H_X * scale), int(H_Y * scale),
         int((H_X + H_W) * scale) - 1, int((H_Y + H_H) * scale) - 1],
        radius=int(CROSS_RX * scale), fill=EMERALD,
    )
    # center circle
    r = int(CR * scale)
    d.ellipse([int((CX - CR) * scale), int((CY - CR) * scale),
               int((CX + CR) * scale), int((CY + CR) * scale)], fill=WHITE)

    if center_text:
        # wordmark at y=570 in a 620-tall canvas -> scale to h
        ty = int(570 * (h / TEXT_H))
        fs = max(10, int(52 * (w / SVG_W)))
        fb = try_load_font(True, fs)
        fr = try_load_font(False, fs)
        # measure "Pharmacy" to center the combined phrase
        bb = fb.getbbox("Pharmacy")
        pw = bb[2] - bb[0]
        bb2 = fr.getbbox("Suite")
        sw = bb2[2] - bb2[0]
        gap = max(4, int(6 * (w / SVG_W)))
        total = pw + gap + sw
        x0 = (w - total) // 2
        d.text((x0, ty), "Pharmacy", font=fb, fill=INDIGO)
        d.text((x0 + pw + gap, ty), "Suite", font=fr, fill=EMERALD)


def render_icon_only(path, size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_icon(d, size, size, center_text=False, font_bold=None, font_reg=None)
    img.save(path)
    return os.path.getsize(path)


def render_icon_text(path, width=512, height=620):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_icon_text_canvas(d, width, height,
                          font_bold=try_load_font(True, 52),
                          font_reg=try_load_font(False, 52))
    img.save(path)
    return os.path.getsize(path)


def draw_icon_text_canvas(d, w, h, font_bold, font_reg):
    """Draw icon (512x512 region at top) + wordmark for a w x h canvas."""
    # icon occupies the top 512 px, centered horizontally if wider
    scale = 512 / SVG_W
    ox = (w - 512) // 2 if w > 512 else 0
    oy = 0
    # background full canvas rounded top/bottom? Keep full-rect with rx=115.
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=RADIUS, fill=BG)
    # vertical pill
    d.rounded_rectangle(
        [ox + V_X, oy + V_Y, ox + V_X + V_W - 1, oy + V_Y + V_H - 1],
        radius=CROSS_RX, fill=INDIGO)
    d.rounded_rectangle(
        [ox + H_X, oy + H_Y, ox + H_X + H_W - 1, oy + H_Y + H_H - 1],
        radius=CROSS_RX, fill=EMERALD)
    r = CR
    d.ellipse([ox + CX - CR, oy + CY - CR, ox + CX + CR, oy + CY + CR], fill=WHITE)
    # wordmark baseline at y=570 (SVG coords) mapped to this canvas's h
    ty = int(570 * (h / TEXT_H))
    bb = font_bold.getbbox("Pharmacy")
    pw = bb[2] - bb[0]
    bb2 = font_reg.getbbox("Suite")
    sw = bb2[2] - bb2[0]
    gap = 6
    total = pw + gap + sw
    x0 = (w - total) // 2
    d.text((x0, ty), "Pharmacy", font=font_bold, fill=INDIGO)
    d.text((x0 + pw + gap, ty), "Suite", font=font_reg, fill=EMERALD)


def main():
    print(f"Rendering logos -> {OUT_DIR}")
    sizes = {
        "logo_512.png": (512, False),
        "logo_with_text_512.png": (512, True),
        "logo_32.png": (32, False),
        "logo_256.png": (256, False),
    }
    for name, (size, with_text) in sizes.items():
        path = os.path.join(OUT_DIR, name)
        if with_text:
            kb = render_icon_text(path, width=size, height=TEXT_H)
        else:
            kb = render_icon_only(path, size)
        print(f"  {name}: {size}x{size}, {kb} bytes")

    # ICO: multi-size 16, 32, 48, 256 from the 512 master (downscaled)
    ico_path = os.path.join(OUT_DIR, "logo.ico")
    ico_sizes = []
    for s in (256, 48, 32, 16):
        master = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        ImageDraw.Draw(master)
        draw_icon(ImageDraw.Draw(master), 256, 256, center_text=False,
                  font_bold=None, font_reg=None)
        img = master.copy()
        if s != 256:
            img = master.resize((s, s), Image.LANCZOS)
        ico_sizes.append(img)
    ico_sizes[0].save(ico_path, format="ICO", sizes=[(s, s) for s, _ in
                     zip((256, 48, 32, 16), ico_sizes)])
    kb = os.path.getsize(ico_path)
    print(f"  logo.ico: multi-size 16/32/48/256, {kb} bytes")
    print("Done.")


if __name__ == "__main__":
    main()
