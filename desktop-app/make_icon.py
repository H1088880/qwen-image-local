# -*- coding: utf-8 -*-
"""Generate the app icon for QwenImageLocal (flat style, pure Pillow)."""
from PIL import Image, ImageDraw
import os

S = 1024          # canvas
R = 232           # rounded corner radius
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 1. diagonal gradient background (2x2 corner colors -> smooth upscale) ----
TL = (34, 211, 238)    # cyan
TR = (56, 189, 248)    # sky blue
BL = (79, 70, 229)     # indigo
BR = (37, 99, 235)     # blue
grad = Image.new("RGB", (2, 2))
grad.putpixel((0, 0), TL)
grad.putpixel((1, 0), TR)
grad.putpixel((0, 1), BL)
grad.putpixel((1, 1), BR)
bg = grad.resize((S, S), Image.BILINEAR).convert("RGBA")

# ---- 2. rounded-square mask ----
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=R, fill=255)

icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
icon.paste(bg, (0, 0), mask)

# ---- 3. white photo card ----
card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(card)
CX0, CY0, CX1, CY1 = 252, 252, 772, 772
d.rounded_rectangle((CX0, CY0, CX1, CY1), radius=72, fill=(255, 255, 255, 255))
icon.alpha_composite(card)

# ---- 4. scene inside the card (clipped by inner rounded rect) ----
scene = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ds = ImageDraw.Draw(scene)
# sun
ds.ellipse((596, 356, 700, 460), fill=(251, 191, 36, 255))       # amber
# back mountain (cyan)
ds.polygon([(392, 700), (560, 470), (728, 700)], fill=(34, 211, 238, 255))
# front mountain (blue)
ds.polygon([(300, 700), (482, 452), (664, 700)], fill=(59, 130, 246, 255))
# clip scene to card's inner rounded rect
inner = Image.new("L", (S, S), 0)
ImageDraw.Draw(inner).rounded_rectangle(
    (CX0 + 40, CY0 + 40, CX1 - 40, CY1 - 40), radius=52, fill=255
)
scene.putalpha(Image.composite(scene.getchannel("A"), Image.new("L", (S, S), 0), inner))
icon.alpha_composite(scene)

# ---- 5. export: multi-size .ico + 256px png preview ----
ico_path = os.path.join(OUT_DIR, "app.ico")
icon.save(ico_path, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
icon.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT_DIR, "app_icon_preview.png"))
print("icon written:", ico_path)
print("sizes ok")
