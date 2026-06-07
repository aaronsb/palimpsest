---
status: Accepted
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-100]
---

# ADR-101: Geometry from OCR, meaning from the LLM

## Context

The original design idea was to overlay a coordinate grid on each page image and
have the LLM read polygon corners off it to produce block geometry. In practice,
vision models are unreliable at precise coordinate regression — a coarse grid
loses precision, a fine grid is unreadable — and the OCR engine (marker/Surya)
*already* emits accurate bounding boxes and reading order. Meanwhile, OCR misses
things the LLM is good at: faint left-page header bands, and leader-line labels
embedded in exploded-view diagrams.

We need a clear division of labor that plays to each component's strength.

## Decision

Assign responsibilities by what each is good at:

- **OCR/marker owns geometry** — bounding boxes (already in PDF native points),
  reading order, block segmentation, and the source text. This is the truth for
  *where* things are.
- **The LLM owns meaning** — translation and block classification (prose,
  step, caption, warning, label, part_number, …), plus *recovery* of text the
  OCR missed.
- **The grid is a shared vocabulary, not a measuring tape.** It is painted on
  the overlay image so the model can *refer to* a region ("untranslated text
  near c3,r19") and so humans can eyeball placement. The model never returns raw
  coordinates.
- For recovered text only (labels/headers OCR missed), the model gives a coarse
  `grid_ref` cell rectangle; we derive an approximate bbox from it. This is the
  single, bounded place where geometry is grid-estimated rather than measured.

Compositors are deterministic and only place what the data already specifies.

## Consequences

### Positive

- Precise, reproducible geometry from the deterministic stage.
- The LLM is used where it excels (language, classification, error correction);
  in the POC it recovered missed headers/labels and even fixed OCR typos from
  the image.
- Sidesteps the VLM coordinate-regression failure mode entirely.

### Negative

- Recovered (grid-estimated) labels are only coarsely placed — fine for
  searchable output (Mode A), but on-the-leader placement needs more work
  (tracked under Mode B, ADR-200).

### Neutral

- Establishes the page-model fields: every block carries both an exact
  `bbox_pt` and a `grid_ref` into the same native-point frame.

## Alternatives Considered

- **LLM reads geometry off the grid (original idea).** Rejected — unreliable
  coordinate regression; precision/legibility trade-off has no good setting.
- **OCR only, no LLM recovery.** Rejected — would silently drop diagram labels
  and left-page headers that OCR cannot read.
