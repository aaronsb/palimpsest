"""Mode A compositor: keep the original scanned page, add an INVISIBLE,
selectable/searchable text layer behind it (the OCR-sandwich technique).

- translatable blocks -> invisible English text positioned at the block bbox
- non-translatable blocks (part_number/identifier) -> invisible *verbatim* text
  so part numbers remain searchable in their original form.

fitz uses points, top-left origin -> bbox_pt maps directly. render_mode=3
makes the inserted text invisible. Usage:
  compose_A.py source.pdf json_dir out.pdf [--lang en]
json files must be named p-NN.page.json with page.slice_idx == NN."""
import glob
import json
import os
import sys
import fitz


def fit_fontsize(page, rect, text, lo=4, hi=28):
    """Largest size whose textbox returns >=0 (fits). Invisible, but we still
    want it spatially sane so search highlights land in the right place."""
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        tmp = fitz.open()
        tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
        rc = tp.insert_textbox(rect, text, fontsize=mid, render_mode=3, align=0)
        tmp.close()
        if rc >= 0:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def main():
    src, json_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    lang = "en"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]

    doc = fitz.open(src)
    by_idx = {}
    for jf in glob.glob(os.path.join(json_dir, "*.page.json")):
        pj = json.load(open(jf))
        by_idx[pj["page"]["slice_idx"]] = pj

    inserted = 0
    for i in range(doc.page_count):
        pj = by_idx.get(i + 1)
        if not pj:
            continue
        page = doc[i]
        for b in pj["blocks"]:
            lng = b.get("lang", {})
            if b.get("translate", True):
                text = lng.get(lang) or lng.get("sv") or ""
            else:
                text = lng.get("sv") or ""  # verbatim part numbers, still searchable
            text = (text or "").strip()
            if not text:
                continue
            rect = fitz.Rect(*b["bbox_pt"])
            if rect.is_empty or rect.width < 2 or rect.height < 2:
                continue
            fs = fit_fontsize(page, rect, text)
            page.insert_textbox(rect, text, fontsize=fs, render_mode=3, align=0)
            inserted += 1

    doc.set_metadata({"title": "Verkstadshandbok grundfordon (translated layer)",
                      "subject": f"searchable {lang} text layer over scan"})
    doc.save(out, garbage=4, deflate=True)
    print(f"compose A -> {out}  ({inserted} invisible text blocks, lang={lang})")


if __name__ == "__main__":
    main()
