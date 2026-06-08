"""Human-readable proof compositor (Mode B-lite).

Builds each output page from the UPRIGHT rendered scan (the IR's pages/p-*.png)
rather than the source PDF, so it is immune to /Rotate flags (760/1028 pages in
the C303 book carry one; marker boxes are in the upright space, matching the PNG).
Over every *translatable* block it paints an opaque white box and renders the
target text fit-to-box; diagrams, part numbers, and untranslated regions show
through. With Surya-detected label boxes (detect_in_figures) this cleanly covers
the original diagram labels and writes the translation in place.

Usage: compose_review.py <pages_dir> <json_dir> <out.pdf> [--lang en]
One output page per p-*.page.json (sorted); pairs with pages/<stem>.png.
"""
import glob
import json
import os
import sys
import fitz

WHITE = (1, 1, 1)
BLACK = (0, 0, 0)


def fit_fontsize(rect, text, lo=4, hi=20):
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        tmp = fitz.open()
        tp = tmp.new_page(width=rect.width + 40, height=rect.height + 40)
        rc = tp.insert_textbox(fitz.Rect(0, 0, rect.width, rect.height), text, fontsize=mid, align=0)
        tmp.close()
        if rc >= 0:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def main():
    pages_dir, json_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "en"

    doc = fitz.open()
    drawn = 0
    for pj_path in sorted(glob.glob(os.path.join(json_dir, "p-*.page.json"))):
        pj = json.load(open(pj_path))
        stem = os.path.basename(pj_path).replace(".page.json", "")
        png = os.path.join(pages_dir, f"{stem}.png")
        w, h = pj["page"]["page_w_pt"], pj["page"]["page_h_pt"]
        page = doc.new_page(width=w, height=h)
        if os.path.exists(png):
            page.insert_image(page.rect, filename=png)

        for b in sorted(pj["blocks"], key=lambda x: x.get("order", 0)):
            if not b.get("translate", True):
                continue
            txt = (b.get("lang", {}).get(lang) or "").strip()
            if not txt:
                continue
            rect = fitz.Rect(*b["bbox_pt"])
            if rect.is_empty or rect.width < 3 or rect.height < 3:
                continue
            # cover the source text, then render the translation in place.
            if b.get("class") == "label":
                # single line, sized to the (precise) box height, centred on it;
                # white pill sized to the text so longer English doesn't wrap.
                fs = max(6.0, min(10.0, rect.height * 0.85))
                tw = fitz.get_text_length(txt, fontname="helv", fontsize=fs)
                cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
                x0, y0 = cx - tw / 2, cy - fs / 2
                page.draw_rect(fitz.Rect(x0 - 1, y0 - 1, x0 + tw + 2, y0 + fs + 2),
                               color=None, fill=WHITE, fill_opacity=1.0)
                page.insert_text((x0, y0 + fs * 0.82), txt, fontsize=fs, color=BLACK)
            else:
                page.draw_rect(rect, color=None, fill=WHITE, fill_opacity=1.0)
                page.insert_textbox(rect, txt, fontsize=fit_fontsize(rect, txt), color=BLACK, align=0)
            drawn += 1

    doc.set_metadata({"title": "Palimpsest review proof",
                      "subject": f"human-readable {lang} render over upright scan"})
    doc.save(out, garbage=4, deflate=True)
    print(f"review proof -> {out}  ({doc.page_count} pages, {drawn} {lang} blocks)")


if __name__ == "__main__":
    main()
