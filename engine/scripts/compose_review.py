"""Human-readable proof compositor (Mode B-lite).

Builds each output page from the UPRIGHT rendered scan (the IR's pages/p-*.png)
rather than the source PDF, so it is immune to /Rotate flags (760/1028 pages in
the C303 book carry one; marker boxes are in the upright space, matching the PNG).
Over every *translatable* block it paints an opaque white mask and renders the
target text in place; diagrams, part numbers, and untranslated regions show
through.

Masking ("trapping") modes:
  fixed (default) — grow the mask a constant amount per side (--trap-x/--trap-y pt)
  auto (--auto-trap) — content-aware: from the block box, grow each side outward
    WHILE the adjacent pixel line still has ink, stopping at the first clean
    (whitespace) line, capped at --trap-cap pt. This hugs glyphs that spill past
    the OCR box yet stops at the gap before a neighbouring diagram stroke.

Usage: compose_review.py <pages_dir> <json_dir> <out.pdf> [--lang en]
                         [--trap-cap 6] [--fixed-trap --trap-x 2.5 --trap-y 1.5]
Content-aware trapping is the default; --fixed-trap reverts to a constant margin.
"""
import glob
import json
import os
import sys
import fitz
import numpy as np
from PIL import Image

WHITE = (1, 1, 1)
BLACK = (0, 0, 0)
INK_THRESH = 110   # grayscale < this = ink (dark on white scan)
MIN_DARK = 3       # >= this many ink px in a line => "has ink" (ignores speckle)
BODY_CLASSES = {"prose", "step"}  # share one font size per page for consistency
FIG_TYPES = {"Picture", "Figure"}  # marker layout types whose interior is artwork


def overlap_frac(rect, fr):
    """Fraction of `rect` covered by `fr` (both fitz.Rect)."""
    ix, iy = max(rect.x0, fr.x0), max(rect.y0, fr.y0)
    ax, ay = min(rect.x1, fr.x1), min(rect.y1, fr.y1)
    if ax <= ix or ay <= iy:
        return 0.0
    a = rect.get_area()
    return ((ax - ix) * (ay - iy) / a) if a else 0.0


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


def fixed_trap(rect, tx, ty):
    return fitz.Rect(rect.x0 - tx, rect.y0 - ty, rect.x1 + tx, rect.y1 + ty)


def auto_trap(rect, ink, dpi, cap_pt, base_pt=1.0):
    """Grow rect (points) per side while the adjacent pixel line has ink, up to
    cap_pt, then pad by base_pt. `ink` is a bool HxW array (True=ink)."""
    s = dpi / 72.0
    H, W = ink.shape
    x0 = max(0, int(rect.x0 * s))
    y0 = max(0, int(rect.y0 * s))
    x1 = min(W, int(rect.x1 * s))
    y1 = min(H, int(rect.y1 * s))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return fixed_trap(rect, base_pt, base_pt)
    cap = max(1, int(cap_pt * s))

    def grow(get_line):
        n = 0
        for step in range(1, cap + 1):
            line = get_line(step)
            if line is None or int(line.sum()) < MIN_DARK:
                break
            n = step
        return n

    nl = grow(lambda k: ink[y0:y1, x0 - k] if x0 - k >= 0 else None)
    nr = grow(lambda k: ink[y0:y1, x1 - 1 + k] if x1 - 1 + k < W else None)
    nt = grow(lambda k: ink[y0 - k, x0:x1] if y0 - k >= 0 else None)
    nb = grow(lambda k: ink[y1 - 1 + k, x0:x1] if y1 - 1 + k < H else None)

    return fitz.Rect((x0 - nl) / s - base_pt, (y0 - nt) / s - base_pt,
                     (x1 + nr) / s + base_pt, (y1 + nb) / s + base_pt)


def main():
    pages_dir, json_dir, out = sys.argv[1], sys.argv[2], sys.argv[3]
    av = sys.argv

    def opt(flag, default):
        return float(av[av.index(flag) + 1]) if flag in av else default

    lang = av[av.index("--lang") + 1] if "--lang" in av else "en"
    auto = "--fixed-trap" not in av          # content-aware trapping is the default (ADR-202)
    trap_cap = opt("--trap-cap", 6.0)
    trap_x = opt("--trap-x", 2.5)
    trap_y = opt("--trap-y", 1.5)

    doc = fitz.open()
    drawn = 0
    for pj_path in sorted(glob.glob(os.path.join(json_dir, "p-*.page.json"))):
        pj = json.load(open(pj_path))
        stem = os.path.basename(pj_path).replace(".page.json", "")
        png = os.path.join(pages_dir, f"{stem}.png")
        w, h = pj["page"]["page_w_pt"], pj["page"]["page_h_pt"]
        dpi = pj["page"]["dpi"]
        page = doc.new_page(width=w, height=h)
        ink = None
        if os.path.exists(png):
            page.insert_image(page.rect, filename=png)
            if auto:
                ink = np.asarray(Image.open(png).convert("L")) < INK_THRESH

        # figure regions: a block whose text sits ON artwork must NOT auto-trap
        # (there is no whitespace line to stop the grow, so it eats the diagram).
        fig_rects = [fitz.Rect(*b["bbox_pt"]) for b in pj["blocks"] if b.get("marker_type") in FIG_TYPES]

        def on_figure(rect, b):
            if b.get("source") == "surya-figure" or b.get("class") == "label":
                return True
            return any(overlap_frac(rect, fr) > 0.35 for fr in fig_rects)

        # gather renderable blocks in reading order
        items = []
        for b in sorted(pj["blocks"], key=lambda x: x.get("order", 0)):
            if not b.get("translate", True):
                continue
            txt = (b.get("lang", {}).get(lang) or "").strip()
            if not txt:
                continue
            rect = fitz.Rect(*b["bbox_pt"])
            if rect.is_empty or rect.width < 3 or rect.height < 3:
                continue
            items.append((b, txt, rect))

        # ONE uniform body font per page: prose + numbered steps share a size so
        # they don't jump line-to-line (use the median of what each box can take).
        body_fits = sorted(fit_fontsize(r, t) for b, t, r in items if b.get("class") in BODY_CLASSES)
        body_fs = body_fits[len(body_fits) // 2] if body_fits else 9.0
        body_fs = max(6.5, min(11.0, body_fs))

        for k, (b, txt, rect) in enumerate(items):
            cls = b.get("class")
            # On artwork: hug the glyphs with a tight fixed pad (auto-trap would
            # grow to the cap and white out the diagram). Elsewhere: content-aware.
            if on_figure(rect, b):
                mask = fixed_trap(rect, 1.0, 1.0)
            elif auto and ink is not None:
                mask = auto_trap(rect, ink, dpi, trap_cap)
            else:
                mask = fixed_trap(rect, trap_x, trap_y)

            if cls == "label":
                # single line centred on the box; mask must also cover the English pill
                fs = max(6.0, min(10.0, rect.height * 0.85))
                tw = fitz.get_text_length(txt, fontname="helv", fontsize=fs)
                cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
                x0, y0 = cx - tw / 2, cy - fs / 2
                mask = mask | fitz.Rect(x0 - 1, y0 - 1, x0 + tw + 1, y0 + fs + 1)
                page.draw_rect(mask, color=None, fill=WHITE, fill_opacity=1.0)
                page.insert_text((x0, y0 + fs * 0.82), txt, fontsize=fs, color=BLACK)
                drawn += 1
                continue

            # let text grow DOWN into the gap before the next block (so a uniform
            # font isn't forced to shrink to a tight box); headings also grow RIGHT
            # since their box is sized to the shorter source word.
            nxt_top = items[k + 1][2].y0 if k + 1 < len(items) else rect.y1 + 6
            bottom = max(rect.y1, min(nxt_top - 1, rect.y1 + 60))
            if cls == "heading":
                rrect = fitz.Rect(rect.x0, rect.y0, min(w - 36, rect.x1 + 220), bottom)
                fs, font = max(10.5, body_fs), "hebo"
            elif cls == "caption":
                rrect = fitz.Rect(rect.x0, rect.y0, rect.x1, bottom)
                fs, font = 8.0, "helv"
            else:  # prose / step / table / other -> uniform body size
                rrect = fitz.Rect(rect.x0, rect.y0, rect.x1, bottom)
                fs, font = body_fs, "helv"
            page.draw_rect(mask, color=None, fill=WHITE, fill_opacity=1.0)
            page.insert_textbox(rrect, txt, fontsize=fs, fontname=font, color=BLACK, align=0)
            drawn += 1

    doc.set_metadata({"title": "Palimpsest review proof",
                      "subject": f"human-readable {lang} render over upright scan"})
    doc.save(out, garbage=4, deflate=True)
    print(f"review proof -> {out}  ({doc.page_count} pages, {drawn} {lang} blocks, "
          f"trap={'auto cap=' + str(trap_cap) if auto else f'fixed {trap_x}/{trap_y}'})")


if __name__ == "__main__":
    main()
