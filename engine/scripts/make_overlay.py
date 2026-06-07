"""Render the grid+box overlay the VLM sees: native page image with a faint
grid, cell coordinate ticks, and each block outlined + numbered by `order`.
The model uses grid coords as a shared vocabulary to *refer to* regions; it
never returns geometry. Usage: make_overlay.py page.json page.png out.png"""
import json
import sys
from PIL import Image, ImageDraw, ImageFont

CLASS_COLOR = {
    "prose": (30, 120, 220), "heading": (200, 30, 30), "step": (30, 160, 90),
    "warning": (230, 120, 0), "caption": (150, 60, 200), "label": (0, 170, 170),
    "part_number": (120, 120, 120), "identifier": (120, 120, 120),
    "header_band": (90, 90, 90), "table": (180, 140, 0), "other": (120, 120, 120),
}


def font(sz):
    for p in ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def main(page_json, page_png, out_png):
    doc = json.load(open(page_json))
    pg, grid = doc["page"], doc["grid"]
    dpi = pg["dpi"]
    s = dpi / 72.0  # pt -> px
    img = Image.open(page_png).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")

    # faint grid
    cw, ch = grid["cell_w_pt"] * s, grid["cell_h_pt"] * s
    for c in range(grid["cols"] + 1):
        d.line([(c * cw, 0), (c * cw, img.height)], fill=(0, 0, 0, 40), width=1)
    for r in range(grid["rows"] + 1):
        d.line([(0, r * ch), (img.width, r * ch)], fill=(0, 0, 0, 40), width=1)
    f_tick = font(int(0.30 * ch))
    for c in range(grid["cols"]):
        d.text((c * cw + 2, 1), str(c), fill=(0, 0, 200, 160), font=f_tick)
    for r in range(grid["rows"]):
        d.text((1, r * ch + 2), str(r), fill=(0, 0, 200, 160), font=f_tick)

    # blocks
    f_lbl = font(max(11, int(0.5 * ch)))
    for b in doc["blocks"]:
        x0, y0, x1, y1 = [v * s for v in b["bbox_pt"]]
        col = CLASS_COLOR.get(b["class"], (120, 120, 120))
        d.rectangle([x0, y0, x1, y1], outline=col + (255,), width=2)
        tag = str(b.get("order", "?"))
        tw = d.textlength(tag, font=f_lbl)
        d.rectangle([x0, y0, x0 + tw + 6, y0 + int(0.6 * ch)], fill=col + (235,))
        d.text((x0 + 3, y0 + 1), tag, fill=(255, 255, 255, 255), font=f_lbl)

    img.save(out_png)
    print(f"overlay -> {out_png} ({len(doc['blocks'])} blocks)")


if __name__ == "__main__":
    main(*sys.argv[1:4])
