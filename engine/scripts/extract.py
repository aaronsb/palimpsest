#!/usr/bin/env python3
"""Palimpsest Extract stage — PDF -> Extract IR.

Produces, under <project>/artifacts/: pages/ (native-res renders), marker/
(marker JSON), json/ (page models = geometry + grid + source text), overlay/
(gridded images for the LLM), and manifest.json (the IR contract header).

Run with the ENGINE venv python (needs Pillow). Shells out to `marker_single`
(its own venv, ROCm torch) for OCR. Deterministic; safe to re-run.

Usage:
  extract.py <project_dir> [--pages FIRST-LAST] [--skip-marker] [--skip-render]

--pages slices the source to PDF pages FIRST..LAST (1-based) for a test run;
omit for the whole document.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_overlay  # noqa: E402

IR_VERSION = "1.0.0"


def sh(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_pad(pages_dir):
    f = sorted(glob.glob(os.path.join(pages_dir, "p-*.png")))[0]
    m = re.search(r"p-(\d+)\.png$", f)
    return len(m.group(1))


def main():
    av = sys.argv
    proj = av[1]
    pages_arg = av[av.index("--pages") + 1] if "--pages" in av else None
    skip_marker = "--skip-marker" in av
    skip_render = "--skip-render" in av

    cfg = json.load(open(os.path.join(proj, "config.json")))
    dpi = cfg.get("dpi", 200)
    cols = cfg.get("grid", {}).get("cols")
    rows = cfg.get("grid", {}).get("rows")
    src_pdf = os.path.join(proj, cfg["source_pdf"])

    art = os.path.join(proj, "artifacts")
    pages_dir = os.path.join(art, "pages")
    marker_dir = os.path.join(art, "marker")
    json_dir = os.path.join(art, "json")
    overlay_dir = os.path.join(art, "overlay")
    for d in (pages_dir, marker_dir, json_dir, overlay_dir):
        os.makedirs(d, exist_ok=True)

    # work pdf (slice if requested)
    first_pdf_page = 1
    work_pdf = src_pdf
    if pages_arg:
        a, b = (int(x) for x in pages_arg.split("-"))
        first_pdf_page = a
        work_pdf = os.path.join(art, f"_work_{a}-{b}.pdf")
        sh(["qpdf", "--empty", "--pages", src_pdf, f"{a}-{b}", "--", work_pdf])

    # 1) render native-res pages
    if not skip_render:
        sh(["pdftoppm", "-r", str(dpi), "-png", work_pdf, os.path.join(pages_dir, "p")])
    pad = detect_pad(pages_dir)
    n_pages = len(glob.glob(os.path.join(pages_dir, "p-*.png")))
    print(f"== rendered {n_pages} pages @ {dpi}dpi, pad={pad}")

    # 2) marker OCR + geometry (GPU via marker's ROCm venv)
    if not skip_marker:
        sh(["marker_single", work_pdf, "--output_format", "json", "--output_dir", marker_dir])
    doc_json = sorted(glob.glob(os.path.join(marker_dir, "**", "*.json"), recursive=True))
    doc_json = [p for p in doc_json if not p.endswith("_meta.json")][0]

    # 3) page models
    cmd = [sys.executable, os.path.join(HERE, "build_page_json.py"), doc_json, json_dir,
           "--first-pdf-page", str(first_pdf_page), "--dpi", str(dpi),
           "--png-dir", pages_dir, "--pad", str(pad)]
    if cols and rows:
        cmd += ["--cols", str(cols), "--rows", str(rows)]
    sh(cmd)

    # 3b) in-figure text detection — precise label boxes from OCR (ADR-201).
    # Runs in the marker venv (surya). Appends source='surya-figure' blocks
    # BEFORE overlays so the LLM sees them on the gridded image.
    if not skip_marker:
        marker_py = os.path.expanduser("~/.local/share/uv/tools/marker-pdf/bin/python")
        try:
            sh([marker_py, os.path.join(HERE, "detect_in_figures.py"), json_dir, pages_dir])
        except subprocess.CalledProcessError as e:
            print(f"WARN: in-figure detection failed, continuing without it: {e}")

    # 4) overlays
    pjs = sorted(glob.glob(os.path.join(json_dir, "p-*.page.json")))
    for pj in pjs:
        stem = os.path.basename(pj).replace(".page.json", "")
        png = os.path.join(pages_dir, f"{stem}.png")
        out = os.path.join(overlay_dir, f"{stem}.grid.png")
        if os.path.exists(png):
            make_overlay.main(pj, png, out)
    print(f"== overlays: {len(glob.glob(os.path.join(overlay_dir, '*.grid.png')))}")

    # 5) manifest (the IR contract header)
    mk_ver = sv_ver = None
    marker_py = os.path.expanduser("~/.local/share/uv/tools/marker-pdf/bin/python")
    try:
        r = subprocess.run(
            [marker_py, "-c", "import importlib.metadata as m;"
             "print(m.version('marker-pdf'));print(m.version('surya-ocr'))"],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            mk_ver, sv_ver = (r.stdout.split() + [None, None])[:2]
    except Exception:
        pass
    pages = []
    for pj in pjs:
        d = json.load(open(pj))
        stem = os.path.basename(pj).replace(".page.json", "")
        pages.append({
            "pdf_page": d["page"]["pdf_page"],
            "page_json": os.path.relpath(pj, art),
            "image": os.path.relpath(os.path.join(pages_dir, f"{stem}.png"), art),
            "overlay": os.path.relpath(os.path.join(overlay_dir, f"{stem}.grid.png"), art),
        })
    manifest = {
        "ir_version": IR_VERSION,
        "doc_id": cfg["name"],
        "source_pdf": cfg["source_pdf"],
        "source_sha256": sha256(src_pdf),
        "source_lang": cfg["source_lang"],
        "page_count": len(pages),
        "dpi": dpi,
        "grid": {"cols": cols, "rows": rows},
        "extractor": {"marker_version": mk_ver, "surya_version": sv_ver, "device": "rocm"},
        "created": None,  # stamp externally; Date is non-deterministic here
        "pages": pages,
    }
    with open(os.path.join(art, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"== manifest.json written: {len(pages)} pages, ir_version {IR_VERSION}")


if __name__ == "__main__":
    main()
