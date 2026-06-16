#!/usr/bin/env python3
"""Generate app icon — G.A.M.M.A. STASH. Requires Pillow."""

import os
import sys
import struct


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(PROJECT_ROOT, "icon.ico")


def generate_ico() -> None:
    """Generate a 256x256 RGBA icon with a STALKER radiation-green theme."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow not available, generating minimal BMP-based ICO.")
        _generate_minimal_ico()
        return

    size = 256
    img = Image.new("RGBA", (size, size), (10, 12, 10, 255))

    draw = ImageDraw.Draw(img)

    # Outer glow ring
    for r in range(120, 80, -1):
        alpha = int(40 * (1 - (r - 80) / 40))
        draw.ellipse([size // 2 - r, size // 2 - r, size // 2 + r, size // 2 + r],
                     outline=(0, 255, 0, alpha), width=3)

    # Three-prong radiation trefoil
    cx, cy = size // 2, size // 2
    r_outer = 55
    r_inner = 18
    r_dot = 10

    # Center circle
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                 outline=(0, 255, 0, 255), fill=(0, 60, 0, 255), width=3)

    # Center dot
    draw.ellipse([cx - r_dot // 2, cy - r_dot // 2, cx + r_dot // 2, cy + r_dot // 2],
                 fill=(0, 255, 0, 255))

    # Three wedge arcs
    import math
    for i in range(3):
        angle = math.radians(120 * i - 90)
        # Outer ring arc
        x0 = cx + r_inner + 5
        y0 = cy - 10
        x1 = cx + r_outer
        y1 = cy + 10

        # Rotate around center
        def rotate(px, py):
            dx, dy = px - cx, py - cy
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a

        pts = [
            rotate(cx + r_inner + 4, cy - 16),
            rotate(cx + r_outer, cy - 10),
            rotate(cx + r_outer, cy + 10),
            rotate(cx + r_inner + 4, cy + 16),
        ]
        draw.polygon([p for pt in pts for p in pt], fill=(0, 200, 0, 220), outline=(0, 255, 0, 255))

    # "G" letter in center
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font = ImageFont.load_default()

    draw.text((cx - 8, cy - 12), "G", fill=(0, 255, 0, 255), font=font)

    # Corner text
    try:
        small_font = ImageFont.truetype("consola.ttf", 11)
    except Exception:
        small_font = ImageFont.load_default()

    draw.text((10, 230), "STASH", fill=(0, 255, 0, 180), font=small_font)

    # Save ICO with multiple sizes
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ICON_PATH, format="ICO", sizes=sizes)
    print(f"Icon created: {ICON_PATH}")


def _generate_minimal_ico() -> None:
    """Generate a minimal valid ICO file without Pillow."""
    # Minimal 32x32 ICO with a simple green pattern
    size = 32
    # BMP data for a 32x32 32-bit image
    width, height = size, size * 2  # ICO spec: height is doubled
    pixels = b""

    for y in range(size):
        for x in range(size):
            # Simple radiation-green gradient with darker corners
            dist = ((x - 16) ** 2 + (y - 16) ** 2) ** 0.5
            if dist < 2:
                r, g, b, a = 255, 255, 255, 255  # center bright
            elif dist < 6:
                g = max(0, min(255, int(200 - dist * 15)))
                r, b, a = 0, 0, 255
            elif dist < 14:
                g = max(0, min(255, int(150 - dist * 10)))
                r, b, a = 5, 0, 255
            else:
                r, g, b, a = 8, 10, 8, 255

            pixels += struct.pack("BBBB", b, g, r, a)

    # BMP info header
    bmp_size = 40 + len(pixels)
    bmp_header = struct.pack("<IiiHHIIiiII",
                             40, width, height, 1, 32, 0, len(pixels), 0, 0, 0, 0)

    # ICO header
    ico_header = struct.pack("<HHH", 0, 1, 1)

    # ICO directory entry
    entry = struct.pack("<BBBBHHII",
                        size, size, 0, 0, 1, 32,  # 32 bpp, no palette
                        bmp_size,  # size of BMP data
                        22)  # offset to BMP data (6 + 16)

    with open(ICON_PATH, "wb") as f:
        f.write(ico_header)
        f.write(entry)
        f.write(bmp_header + pixels)

    print(f"Minimal icon created: {ICON_PATH}")


if __name__ == "__main__":
    generate_ico()
