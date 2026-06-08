"""Stage 5 merge: fold an LLM translate+classify result into a page model.

The LLM returns:
  { "blocks":    [ {uid, class, translate, en} ... ],   # existing marker blocks
    "recovered": [ {grid_ref:{c0,r0,c1,r1}, class, sv, en} ... ] }  # text marker MISSED

Existing blocks keep their precise marker bbox; we only update class/translate/
lang.en. Recovered blocks (leader-labels, missed headers) get an APPROXIMATE
bbox derived from their grid cell rectangle — the one place we accept
grid-estimated geometry, per spec. Usage:
  apply_translation.py page.json llm.json [out.json]
"""
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from grid_lib import bbox_to_grid_ref  # noqa: E402


def cell_rect_to_pt(gr, grid):
    cw, ch = grid["cell_w_pt"], grid["cell_h_pt"]
    return [round(gr["c0"] * cw, 2), round(gr["r0"] * ch, 2),
            round((gr["c1"] + 1) * cw, 2), round((gr["r1"] + 1) * ch, 2)]


def main():
    page_f, llm_f = sys.argv[1], sys.argv[2]
    out_f = sys.argv[3] if len(sys.argv) > 3 else page_f
    pj = json.load(open(page_f))
    # strict=False tolerates raw control chars (e.g. a literal newline a model
    # left inside a translated string) instead of aborting the whole page.
    llm = json.load(open(llm_f), strict=False)
    grid = pj["grid"]

    upd = {b["uid"]: b for b in llm.get("blocks", [])}
    for b in pj["blocks"]:
        u = upd.get(b["uid"])
        if not u:
            continue
        if u.get("class"):
            b["class"] = u["class"]
        if "translate" in u:
            b["translate"] = u["translate"]
        if u.get("en") is not None:
            b["lang"]["en"] = u["en"]

    prefix = pj["blocks"][0]["uid"].rsplit("-b", 1)[0] if pj["blocks"] else f"pg{pj['page']['pdf_page']}"
    for i, r in enumerate(llm.get("recovered", [])):
        gr = r["grid_ref"]
        bbox = cell_rect_to_pt(gr, grid)
        pj["blocks"].append({
            "uid": f"{prefix}-r{i:02d}",
            "order": 1000 + i,
            "marker_type": None,
            "bbox_pt": bbox,
            "grid_ref": bbox_to_grid_ref(bbox, grid),
            "class": r.get("class", "label"),
            "translate": r.get("class") not in ("part_number", "identifier"),
            "lang": {k: v for k, v in (("sv", r.get("sv")), ("en", r.get("en"))) if v},
            "ocr_conf": None,
            "notes": "recovered by vision pass (grid-estimated bbox)",
        })

    json.dump(pj, open(out_f, "w"), ensure_ascii=False, indent=2)
    n_up = sum(1 for b in pj["blocks"] if b["lang"].get("en"))
    print(f"{out_f}: {n_up}/{len(pj['blocks'])} blocks have en; "
          f"+{len(llm.get('recovered', []))} recovered")


if __name__ == "__main__":
    main()
