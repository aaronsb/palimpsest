"""Human-readable proof compositor (Mode B-lite).

Keeps the original scanned page as the background, but over every *translatable*
text block paints an opaque white box and renders the English in place. Diagram
regions, part numbers, and anything translate=false are left showing through, so
you get readable English prose/steps/headings/captions/labels while the exploded
views and identifiers stay intact. Good enough to READ and review without the
full Mode-B inpainting/anchoring work.

Usage: compose_review.py source.pdf json_dir out.pdf [--lang en]
json files named p-NN.page.json with page.slice_idx == NN.
"""
import glob
import json
import os
import sys
import fitz

WHITE = (1, 1, 1)
BLACK = (0, 0, 0)


def fit_fontsize(rect, text, page_w, page_h, lo=4, hi=20):
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        tmp = fitz.open()
        tp = tmp.new_page(width=page_w, height=page_h)
        rc = tp.insert_textbox(rect, text, fontsize=mid, align=0)
        tmp.close()
        if rc >= 0:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def main():
    src, json_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "en"

    doc = fitz.open(src)
    by_idx = {}
    for jf in glob.glob(os.path.join(json_dir, "*.page.json")):
        pj = json.load(open(jf))
        by_idx[pj["page"]["slice_idx"]] = pj

    drawn = 0
    for i in range(doc.page_count):
        pj = by_idx.get(i + 1)
        if not pj:
            continue
        page = doc[i]
        pw, ph = page.rect.width, page.rect.height
        # paint text blocks back-to-front by reading order
        for b in sorted(pj["blocks"], key=lambda x: x.get("order", 0)):
            if not b.get("translate", True):
                continue
            en = (b.get("lang", {}).get(lang) or "").strip()
            if not en:
                continue
            rect = fitz.Rect(*b["bbox_pt"])
            if rect.is_empty or rect.width < 3 or rect.height < 3:
                continue
            is_label = b.get("class") == "label"
            if is_label:
                # diagram leader-label: small fixed font, tight white pill sized
                # to the text (keeps the exploded view readable) at the box's
                # top-left anchor. Full anchoring to the leader line is Mode-B work.
                fs = 8
                tw = fitz.get_text_length(en, fontname="helv", fontsize=fs)
                x0, y0 = rect.x0, rect.y0
                pill = fitz.Rect(x0 - 1, y0 - 1, x0 + tw + 2, y0 + fs + 2)
                page.draw_rect(pill, color=None, fill=WHITE, fill_opacity=1.0)
                page.insert_text((x0, y0 + fs), en, fontsize=fs, color=BLACK)
            else:
                page.draw_rect(rect, color=None, fill=WHITE, fill_opacity=1.0)
                fs = fit_fontsize(rect, en, pw, ph)
                page.insert_textbox(rect, en, fontsize=fs, color=BLACK, align=0)
            drawn += 1

    doc.set_metadata({"title": "Palimpsest review proof (English)",
                      "subject": f"human-readable {lang} render over original scan"})
    doc.save(out, garbage=4, deflate=True)
    print(f"review proof -> {out}  ({drawn} English blocks rendered, lang={lang})")


if __name__ == "__main__":
    main()
