"""Stage 3: marker Document JSON -> per-page page model (our canonical schema).

marker emits bbox ALREADY in PDF native points (top-left origin) -> no DPI
conversion needed for geometry. We flatten marker's block tree into leaf text
units in reading order, map block_type -> our class, parse the header band for
stable UIDs, attach the grid + grid_ref. Translations (lang.en, refined class)
are filled later by the LLM stage.

Usage: build_page_json.py marker_doc.json out_dir --first-pdf-page 296 --dpi 200 --png-dir poc/pages
"""
import json
import os
import re
import sys
from html import unescape

sys.path.insert(0, os.path.dirname(__file__))
from grid_lib import make_grid, bbox_to_grid_ref  # noqa: E402

from PIL import Image  # noqa: E402

# marker block_type -> (our class, translate?)
CLASS_MAP = {
    "PageHeader": ("header_band", False),
    "PageFooter": ("header_band", False),
    "SectionHeader": ("heading", True),
    "Text": ("prose", True),
    "TextInlineMath": ("prose", True),
    "ListItem": ("step", True),
    "Caption": ("caption", True),
    "Footnote": ("prose", True),
    "Table": ("table", True),
    "TableCell": ("table", True),
    "Figure": ("other", False),
    "Picture": ("other", False),
    "Equation": ("identifier", False),
    "Code": ("identifier", False),
    "Handwriting": ("prose", True),
}
# container types we recurse THROUGH (no own text)
GROUPS = {"PictureGroup", "FigureGroup", "TableGroup", "ListGroup", "Page", "Document"}

# Header tokens appear in either order across left/right pages (e.g.
# "Del 1 Flik 1 Sida 67" vs "Sida 64 ... Del 1 Flik 1"), so match each
# independently rather than as a fixed sequence.
DEL_RE = re.compile(r"Del\s+(\w+)", re.I)
FLIK_RE = re.compile(r"Flik\s+(\w+)", re.I)
SIDA_RE = re.compile(r"Sida\s+(\w+)", re.I)


def strip_html(h):
    return unescape(re.sub(r"<[^>]+>", " ", h or "")).strip()


def leaves(block):
    """Yield leaf blocks in reading order (recurse through groups)."""
    kids = block.get("children")
    if kids and block.get("block_type") in GROUPS:
        for k in kids:
            yield from leaves(k)
    elif kids:  # non-group with children: emit self if it has text, else recurse
        if strip_html(block.get("html")):
            yield block
        else:
            for k in kids:
                yield from leaves(k)
    else:
        yield block


def parse_header(text_blocks):
    """Find Del/Flik/Sida anywhere on the page, order-independent. Prefer a
    single block carrying Sida (the header band) but fall back to page-wide."""
    joined = "  ".join(text_blocks)
    d = DEL_RE.search(joined)
    f = FLIK_RE.search(joined)
    s = SIDA_RE.search(joined)
    raw = next((t for t in text_blocks if SIDA_RE.search(t)), None)
    return (d.group(1) if d else None,
            f.group(1) if f else None,
            s.group(1) if s else None,
            raw)


def build_page(page, pdf_page, slice_idx, dpi, png_path, cols=None, rows=None):
    page_w, page_h = page["bbox"][2], page["bbox"][3]
    grid = make_grid(page_w, page_h, *( (cols, rows) if cols and rows else () ))
    px_w = px_h = None
    if png_path and os.path.exists(png_path):
        px_w, px_h = Image.open(png_path).size

    raw = [b for b in leaves(page)]
    texts = [strip_html(b.get("html")) for b in raw]
    delv, flikv, sidav, hdr_raw = parse_header(texts)
    sid = f"s{int(sidav):03d}" if (sidav and sidav.isdigit()) else (f"s{sidav}" if sidav else None)
    prefix = (f"d{delv}-f{flikv}-{sid}" if (delv and flikv and sid)
              else f"pg{pdf_page}")

    blocks = []
    for i, (b, txt) in enumerate(zip(raw, texts)):
        cls, translate = CLASS_MAP.get(b.get("block_type"), ("other", bool(txt)))
        bbox = [round(v, 2) for v in b["bbox"]]
        blocks.append({
            "uid": f"{prefix}-b{i:02d}",
            "order": i,
            "marker_type": b.get("block_type"),
            "bbox_pt": bbox,
            "grid_ref": bbox_to_grid_ref(bbox, grid),
            "class": cls,
            "translate": translate and bool(txt),
            "lang": {"sv": txt},
            "ocr_conf": None,
            "notes": None,
        })

    return {
        "page": {
            "pdf_page": pdf_page, "slice_idx": slice_idx, "dpi": dpi,
            "page_w_pt": page_w, "page_h_pt": page_h, "px_w": px_w, "px_h": px_h,
            "header": {"del": delv, "flik": flikv, "sida": sidav,
                       "authority": None, "raw": hdr_raw},
        },
        "grid": grid,
        "blocks": blocks,
    }


def _opt(name, cast, default=None):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def main():
    doc_json, out_dir = sys.argv[1], sys.argv[2]
    first = _opt("--first-pdf-page", int, 1)
    dpi = _opt("--dpi", int, 200)
    png_dir = _opt("--png-dir", str, None)
    pad = _opt("--pad", int, 2)
    cols = _opt("--cols", int, None)
    rows = _opt("--rows", int, None)
    os.makedirs(out_dir, exist_ok=True)
    doc = json.load(open(doc_json))

    for idx, page in enumerate(doc["children"]):
        slice_idx = idx + 1
        pdf_page = first + idx
        png = os.path.join(png_dir, f"p-{slice_idx:0{pad}d}.png") if png_dir else None
        pj = build_page(page, pdf_page, slice_idx, dpi, png, cols, rows)
        out = os.path.join(out_dir, f"p-{slice_idx:0{pad}d}.page.json")
        json.dump(pj, open(out, "w"), ensure_ascii=False, indent=2)
        hdr = pj["page"]["header"]
        print(f"p-{slice_idx:0{pad}d} (pdf {pdf_page}) "
              f"Del{hdr['del']}/Flik{hdr['flik']}/Sida{hdr['sida']} "
              f"{len(pj['blocks'])} blocks")


if __name__ == "__main__":
    main()
