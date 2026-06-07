# C303 Workshop Manual — Translation & Reconstruction Pipeline

**Source:** `Grund.pdf` — *Verkstadshandbok grundfordon*, Terrängbil 11 och 13
(Volvo C303/C304). 1028 pp, scanned 200 DPI, A4, **no text layer**. Source
language **Swedish (`sv`)**.

**Goal:** a searchable, queryable, multilingual reconstruction. Every scrap of
text on every page is captured once, keyed by a stable UID, translated, and
classified. Two render targets share one data model:

- **Mode A — searchable bilingual original** *(build first)*: keep the scan,
  add an *invisible* text layer (per language) behind it. Fully
  searchable/queryable; diagrams untouched; no text-fitting problem.
- **Mode B — visual reproduction** *(later, same JSON)*: white-out/inpaint the
  Swedish text regions, render the translated text in place.

The LLM never draws and never invents geometry. Rendering is 100% deterministic.

---

## Coordinate model (the canonical frame)

There is **one canonical coordinate space: the PDF page's native point space**
(1 pt = 1/72"). It is resolution-independent and is what the Mode-A/B
compositors emit into. Everything spatial in the page JSON lives in this frame.

The raster the LLM and OCR see is a render of that page at a known DPI. We store
the raster dims and DPI so any pixel-space artifact (marker boxes, overlay
images) maps losslessly back to native points:

```
px_to_pt = 72 / dpi          pt_to_px = dpi / 72
x_pt = x_px * 72 / dpi        (origin top-left, y grows downward in both)
```

> Note: native PDF text space has origin bottom-left; we standardize the JSON on
> **top-left origin** (image convention) and let the compositor flip for PDF.

### The grid

Each page carries an explicit **grid** object, defined **in the canonical native
point space** (per your spec — the grid is always referenced against the PDF's
native resolution, never against an arbitrary raster size). The grid is a
uniform lattice over the page box:

```json
"grid": {
  "space": "pdf_pt",
  "page_w_pt": 595.0, "page_h_pt": 842.0,
  "cols": 24, "rows": 34,
  "cell_w_pt": 24.79, "cell_h_pt": 24.76,
  "origin": "top-left"
}
```

- Cell `(c, r)` covers `[c*cell_w_pt, (c+1)*cell_w_pt) × [r*cell_h_pt, (r+1)*cell_h_pt)`.
- Columns `0..cols-1` left→right; rows `0..rows-1` top→bottom.
- The grid is painted onto the overlay image the LLM sees, so the model has a
  shared vocabulary to *refer to* regions ("there is untranslated text around
  c3,r19") even though it never returns raw coordinates.

Every block stores BOTH:
- `bbox_pt` — exact rectangle in native points (the truth, from OCR), and
- `grid_ref` — the integer cell rectangle it occupies `{c0,r0,c1,r1}`
  (derived deterministically from `bbox_pt`; legible, diffable, LLM-facing).

---

## Stable UIDs

UIDs are **deterministic and structural**, never a random running counter (so
re-runs are idempotent and diffable):

```
<del>-<flik>-s<sida>-b<NN>
e.g.  d1-f1-s067-b03
```

`del`/`flik`/`sida` are parsed deterministically from the page **header band**
(`Del 1 · Flik 1 · Sida 67`), which is the manual's native structure — this also
yields the real TOC/section tree for free. `bNN` is the block's index in reading
order on that page. If the header is unreadable, fall back to
`pg<absolute_pdf_page>-bNN`.

---

## Per-page artifacts (idempotent, resumable, page-addressable)

Each page is an independent unit. Re-running any stage overwrites only its own
artifact.

| Stage | Tool (deterministic unless noted) | Artifact |
|---|---|---|
| 1 render | `pdftoppm` @ native DPI | `pages/p-NN.png` |
| 2 OCR + geometry | `marker` (Surya) | `marker/…/*.json` |
| 3 page model | builder script | `json/p-NN.page.json` (geometry + grid, empty translations) |
| 4 overlay | PIL script | `overlay/p-NN.grid.png` (boxes + indices + grid) |
| 5 translate+classify | **LLM (vision)** | fills `lang.en` + `class` per block in the page JSON |
| 6 glossary | accumulate/normalize | `glossary.json` (sv→en term map, fed back into step 5) |
| 7 compose A | PyMuPDF | `out/p-NN.A.pdf` (scan + invisible text layers) |
| 8 QA | deterministic checks + cheap VLM | `qa/p-NN.json` |

---

## Block classes

The LLM classifies every text region. Class drives translation + render policy:

| class | translate? | Mode-A layer | Mode-B render |
|---|---|---|---|
| `prose` | yes | invisible en/sv | replace in place, shrink-to-fit |
| `heading` | yes | invisible | replace |
| `step` (numbered) | yes (keep number) | invisible | replace |
| `warning` (VARNING) | yes | invisible | replace |
| `caption` (Bild N.) | yes (keep "Bild N"→"Fig N") | invisible | replace |
| `label` (leader line) | yes, short | invisible | replace, stay anchored to leader |
| `part_number` / `identifier` | **no** (copy verbatim) | invisible (searchable) | leave original pixels |
| `header_band` | structural parse only | invisible | leave original |

Part numbers and identifiers must be **byte-identical** source→output (a QA
check). They are searchable but never translated.

---

## Translation quality levers

- **Glossary / translation memory:** one sv→en mapping per technical term,
  enforced across all 1028 pp (`Kolv`→piston everywhere). Built incrementally,
  fed into every page prompt.
- **Multilingual from day one:** the `lang` map holds `sv` (source) + `en` now;
  `de`/`es` are added later as extra keys against the *same* UIDs — no
  re-segmentation.

## QA (step 8) — split by what's actually checkable

- **Deterministic:** leftover Swedish characters (åäö) in `en`; part-number /
  digit drift sv↔en; box overflow / clipping in rendered output; UID
  uniqueness; reading-order sanity.
- **Cheap VLM (Haiku):** visual sanity of the composed page — does text sit in
  the right place, anything obviously untranslated or garbled. This is a
  layout/consistency check, **not** a translation-quality judge.

## Relation to existing standards (interop, less custom code)

- Mode-A invisible text layer ≡ the standard OCR "sandwich" (cf. `ocrmypdf`).
- `lang` map of UID→{src,targets} ≡ **XLIFF** translation units.
- OCR boxes ≡ **hOCR / ALTO**. Page JSON is a superset tailored to the grid.

## Scale notes (full run, later)

- Swap the marker venv's CUDA torch for **ROCm** to use the RX 7900 XTX (24 GB);
  CPU is POC-only.
- 1028 independent pages → embarrassingly parallel fan-out; each page resumable.
- Watch terminology drift → glossary is the main defense.
