#!/usr/bin/env python3
"""Recover text INSIDE figure regions with precise OCR boxes (ADR-101).

marker's layout step collapses exploded-view diagrams into a single Picture
block, dropping the leader-labels inside. This pass crops each figure region
from the upright page render and runs Surya detection+recognition on just that
crop, then appends every found line as a block with a PRECISE bbox (from OCR,
not grid-estimated) + source text. The translate stage then translates them in
place, so labels overlay cleanly over the originals.

Runs in the MARKER venv (surya + ROCm torch):
  ~/.local/share/uv/tools/marker-pdf/bin/python engine/scripts/detect_in_figures.py \
      <json_dir> <pages_dir> [--debug-dir D] [--limit N] [--min-conf 0.5]

Idempotent: removes prior source='surya-figure' blocks before re-adding.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid_lib import bbox_to_grid_ref  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

FIG_TYPES = {"Picture", "Figure"}


def center_in(inner, outer):
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def line_bbox(line):
    if getattr(line, "bbox", None):
        return list(line.bbox)
    poly = line.polygon
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def main():
    json_dir, pages_dir = sys.argv[1], sys.argv[2]
    debug_dir = sys.argv[sys.argv.index("--debug-dir") + 1] if "--debug-dir" in sys.argv else None
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    min_conf = float(sys.argv[sys.argv.index("--min-conf") + 1]) if "--min-conf" in sys.argv else 0.7
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)

    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor
    from surya.detection import DetectionPredictor
    from surya.settings import settings as ss

    foundation = FoundationPredictor(checkpoint=ss.RECOGNITION_MODEL_CHECKPOINT)
    rec = RecognitionPredictor(foundation)
    det = DetectionPredictor()

    files = sorted(glob.glob(os.path.join(json_dir, "p-*.page.json")))
    if limit:
        files = files[:limit]
    total_added = 0

    for jf in files:
        d = json.load(open(jf))
        stem = os.path.basename(jf).replace(".page.json", "")
        png = os.path.join(pages_dir, f"{stem}.png")
        if not os.path.exists(png):
            continue
        dpi = d["page"]["dpi"]
        s = dpi / 72.0  # pt -> px
        img = Image.open(png).convert("RGB")
        grid = d["grid"]

        # drop prior detections (idempotent) and index existing text boxes
        d["blocks"] = [b for b in d["blocks"] if b.get("source") != "surya-figure"]
        existing = [b["bbox_pt"] for b in d["blocks"] if (b.get("lang", {}).get("sv") or "").strip()]
        figs = [b for b in d["blocks"] if b.get("marker_type") in FIG_TYPES]
        if not figs:
            continue

        crops, origins = [], []
        for fb in figs:
            x0, y0, x1, y1 = (v * s for v in fb["bbox_pt"])
            x0, y0 = max(0, int(x0)), max(0, int(y0))
            x1, y1 = min(img.width, int(x1)), min(img.height, int(y1))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            crops.append(img.crop((x0, y0, x1, y1)))
            origins.append((x0, y0))
        if not crops:
            continue

        results = rec(crops, det_predictor=det)
        prefix = d["blocks"][0]["uid"].rsplit("-b", 1)[0] if d["blocks"] else stem
        added = 0
        dbg = ImageDraw.Draw(img) if debug_dir else None
        for res, (ox, oy) in zip(results, origins):
            for line in res.text_lines:
                txt = (line.text or "").strip()
                conf = getattr(line, "confidence", 1.0)
                if not txt or conf < min_conf:
                    continue
                if not any(c.isalnum() for c in txt):       # pure punctuation/marks
                    continue
                if len(txt) < 2 and conf < 0.9:             # stray single-char OCR noise
                    continue
                lx0, ly0, lx1, ly1 = line_bbox(line)
                bbox_pt = [round((ox + lx0) / s, 2), round((oy + ly0) / s, 2),
                           round((ox + lx1) / s, 2), round((oy + ly1) / s, 2)]
                if any(center_in(bbox_pt, e) for e in existing):
                    continue
                d["blocks"].append({
                    "uid": f"{prefix}-f{added:02d}",
                    "order": 2000 + added,
                    "marker_type": None,
                    "source": "surya-figure",
                    "bbox_pt": bbox_pt,
                    "grid_ref": bbox_to_grid_ref(bbox_pt, grid),
                    "class": "label",
                    "translate": True,
                    "lang": {"sv": txt},
                    "ocr_conf": round(getattr(line, "confidence", 0.0), 3),
                    "notes": "in-figure text, precise OCR bbox",
                })
                if dbg:
                    dbg.rectangle([(ox + lx0), (oy + ly0), (ox + lx1), (oy + ly1)],
                                  outline=(220, 0, 0), width=2)
                added += 1
        json.dump(d, open(jf, "w"), ensure_ascii=False, indent=2)
        if dbg:
            img.save(os.path.join(debug_dir, f"{stem}.det.png"))
        total_added += added
        print(f"{stem}: +{added} in-figure lines")

    print(f"== done: {total_added} in-figure text lines across {len(files)} pages")


if __name__ == "__main__":
    main()
