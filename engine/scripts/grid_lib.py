"""Shared geometry: the canonical frame is PDF native points, top-left origin.
The grid is defined in that same frame (per spec: grid always references the
PDF's native resolution, never an arbitrary raster size)."""

DEFAULT_COLS = 24
DEFAULT_ROWS = 34


def make_grid(page_w_pt, page_h_pt, cols=DEFAULT_COLS, rows=DEFAULT_ROWS):
    return {
        "space": "pdf_pt",
        "cols": cols,
        "rows": rows,
        "cell_w_pt": page_w_pt / cols,
        "cell_h_pt": page_h_pt / rows,
        "origin": "top-left",
    }


def bbox_to_grid_ref(bbox_pt, grid):
    """Inclusive cell rectangle a bbox occupies."""
    x0, y0, x1, y1 = bbox_pt
    cw, ch = grid["cell_w_pt"], grid["cell_h_pt"]
    c0 = max(0, min(grid["cols"] - 1, int(x0 // cw)))
    r0 = max(0, min(grid["rows"] - 1, int(y0 // ch)))
    c1 = max(0, min(grid["cols"] - 1, int((x1 - 1e-6) // cw)))
    r1 = max(0, min(grid["rows"] - 1, int((y1 - 1e-6) // ch)))
    return {"c0": c0, "r0": r0, "c1": c1, "r1": r1}


def px_to_pt(v, dpi):
    return v * 72.0 / dpi


def pt_to_px(v, dpi):
    return v * dpi / 72.0
