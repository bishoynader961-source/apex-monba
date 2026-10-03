"""Build a genuine multi-size ICO (16, 32, 48, 256) for Pharmacy Suite.

ICO format (Windows):
  ICONDIR: reserved(2) type(2)=1 num_images(2)
  ICONDIRENTRY[n]: bWidth(1) bHeight(1) bColorCount(1) bReserved(1)
                   bPlanes(2) bBitCount(2) dwBytesInRes(4) dwImageOffset(4)
  Image data[n]: BITMAPINFOHEADER(40) + pixel rows (bottom-up, 32bpp BGRA,
                 row padded to 4 bytes) + 1bpp AND mask (h rows, stride
                 ((w+31)//32)*4). biHeight in header = 2*h (XOR + mask).

We render the icon at 256x256 then downscale for 16/32/48.
"""
from __future__ import annotations
import struct
from PIL import Image, ImageDraw

# ---- icon geometry (matches SVG: 512 viewBox) ----
V_X, V_Y, V_W, V_H = 216, 106, 80, 300
H_X, H_Y, H_W, H_H = 106, 216, 300, 80
CX, CY, CR = 256, 256, 26
RADIUS, CROSS_RX = 115, 40
BG      = (0xEE, 0xF2, 0xFF, 255)
INDIGO  = (0x4F, 0x46, 0xE5, 255)
EMERALD = (0x10, 0xB9, 0x81, 232)
WHITE   = (255, 255, 255, 255)

def draw_icon(img: Image.Image) -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                        radius=RADIUS, fill=BG)
    d.rounded_rectangle([V_X, V_Y, V_X + V_W - 1, V_Y + V_H - 1],
                        radius=CROSS_RX, fill=INDIGO)
    d.rounded_rectangle([H_X, H_Y, H_X + H_W - 1, H_Y + H_H - 1],
                        radius=CROSS_RX, fill=EMERALD)
    d.ellipse([CX - CR, CY - CR, CX + CR, CY + CR], fill=WHITE)

def render_at(size: int) -> Image.Image:
    if size == 256:
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        draw_icon(img)
        return img
    big = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw_icon(big)
    return big.resize((size, size), Image.LANCZOS)

def rgba_to_bgra_bottom_up(img: Image.Image) -> bytes:
    """32bpp BGRA pixels, bottom-up, 4-byte row padding."""
    w, h = img.size
    row = w * 4
    pad = (4 - (row % 4)) % 4
    out = bytearray()
    px = img.load()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = px[x, y]
            out += struct.pack("<BBBB", b, g, r, a)
        out += b"\x00" * pad
    return bytes(out)

def and_mask_bytes(w: int, h: int) -> bytes:
    """1bpp AND mask: h rows, ((w+31)//32)*4 bytes per row, all zero."""
    stride = ((w + 31) // 32) * 4
    return b"\x00" * (stride * h)

def encode_bmp(img: Image.Image) -> bytes:
    """Return ICO image data: BITMAPINFOHEADER + BGRA pixels + AND mask.
    biHeight = 2 * h (XOR image + AND mask per ICO spec)."""
    w, h = img.size
    pixels = rgba_to_bgra_bottom_up(img)
    header = struct.pack("<IiiHHIIiiII",
        40,          # biSize
        w, 2 * h,    # biWidth, biHeight (doubled)
        1, 32,       # biPlanes, biBitCount
        0,           # biCompression = BI_RGB
        len(pixels), # biSizeImage
        0, 0,        # biXPelsPerMeter, biYPelsPerMeter
        0, 0)        # biClrUsed, biClrImportant
    return header + pixels + and_mask_bytes(w, h)

def _byte_dim(d: int) -> int:
    """ICO byte dimension: 1-255 as-is, 256 encoded as 0."""
    return 0 if d == 256 else d


def build_ico(path: str, sizes: list[int]) -> int:
    frames = []
    for s in sizes:
        img = render_at(s)
        data = encode_bmp(img)
        frames.append((s, s, len(data), data))

    # ICONDIR + entries
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + len(sizes) * 16
    entries = b""
    for w, h, size, data in frames:
        entries += struct.pack("<BBBBHHII",
            _byte_dim(w), _byte_dim(h), 0, 0,  # width, height, color count, reserved
            1, 32,                                # planes, bit count
            size, offset)                         # dwBytesInRes, dwImageOffset
        offset += size

    blob = header + entries + b"".join(d for *_, d in frames)
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)

if __name__ == "__main__":
    import os
    p = os.path.join(os.path.dirname(__file__), "logo.ico")
    n = build_ico(p, [16, 32, 48, 256])
    print(f"logo.ico written: {n} bytes")

    # verify header
    data = open(p, "rb").read()
    reserved, typ, count = struct.unpack_from("<HHH", data, 0)
    print(f"ICONDIR: reserved={reserved} type={typ} images={count}")
    off = 6
    for i in range(count):
        vals = struct.unpack_from("<BBBBHHII", data, off)
        print(f"  image {i+1}: {vals[0]}x{vals[1]} "
              f"colors={vals[2]} planes/bits={vals[4]}/{vals[5]} "
              f"size={vals[6]} offset={vals[7]}")
        off += 16
    print("OK" if count == 4 else "FAIL: expected 4 images")
