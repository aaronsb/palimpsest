"""Emit a slim translate-view of each page for the LLM stage.

The translate agent only needs to classify + translate each block — it does NOT
need geometry (bbox_pt, grid_ref), provenance (source, marker_type, ocr_conf), or
notes; those belong to the compositor and are keyed back by uid via
apply_translation.py. Carrying them into the prompt is what blows the context
window on dense figure pages (a 169-block page is ~84 KB / ~20k tokens of JSON
the model never uses).

This writes a minimal `{blocks:[{uid, order, class, <src>}]}` per page so many
pages fit in one agent (better prompt-cache reuse of the shared glossary/context).

Usage: translate_view.py <json_dir> <out_dir> [--src sv] [--pages 0161 0162 ...]
"""
import glob
import json
import os
import sys


def main():
    json_dir, out_dir = sys.argv[1], sys.argv[2]
    av = sys.argv
    src = av[av.index("--src") + 1] if "--src" in av else "sv"
    pages = av[av.index("--pages") + 1:] if "--pages" in av else None

    os.makedirs(out_dir, exist_ok=True)
    if pages:
        files = [os.path.join(json_dir, f"p-{p}.page.json") for p in pages]
    else:
        files = sorted(glob.glob(os.path.join(json_dir, "p-*.page.json")))

    n = blocks = 0
    for f in files:
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        slim = []
        for b in d.get("blocks", []):
            slim.append({
                "uid": b["uid"],
                "order": b.get("order"),
                "class": b.get("class"),
                src: (b.get("lang", {}) or {}).get(src, ""),
            })
        out = os.path.join(out_dir, os.path.basename(f))
        json.dump({"blocks": slim}, open(out, "w"), ensure_ascii=False)
        n += 1
        blocks += len(slim)
    print(f"translate-view: {n} pages, {blocks} blocks -> {out_dir}")


if __name__ == "__main__":
    main()
