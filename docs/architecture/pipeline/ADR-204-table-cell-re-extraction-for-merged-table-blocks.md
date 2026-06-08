---
status: Accepted
date: 2026-06-08
deciders:
  - aaronsb
related: [ADR-100, ADR-101, ADR-201, ADR-202, ADR-203]
---

# ADR-204: Table cell re-extraction for merged table blocks

## Context

Most tables in the source survive Extract with structure intact — marker emits
**190 `Table` containers and 1688 `TableCell` blocks** across the book, each cell a
separate block with its own bbox. The compositor renders per block, so those
tables translate and compose fine, cell by cell.

But on **~136 pages** marker collapses an entire table into **one block** (a
`Table`/`TableOfContents`/`SectionHeader` block carrying 200–6600 chars of the
whole table's text, with no `TableCell` children on the page). The translate stage
then renders that as a single wrapped paragraph — a wall of text with no rows or
columns, which the reviewer flagged as unreadable. The data is present; the
*structure* was lost upstream.

Per ADR-101 the LLM must not be the source of geometry, so re-segmenting the blob
by asking the model to guess cell boundaries is out. The structure has to come
from a deterministic recognizer, exactly as in-figure label geometry does
(ADR-201).

## Decision

Add a deterministic **table re-extraction sub-pass** to the Extract stage
(`engine/scripts/detect_tables.py`), mirroring ADR-201's in-figure detection:

1. Identify merged-blob table blocks (large single block, table-ish `marker_type`
   or `class`, page has no `TableCell` blocks of its own).
2. Crop that region from the upright render and run **Surya `TableRecPredictor`**
   (confirmed available in the marker venv) to recover cell bboxes + row/column
   structure; OCR each cell for its source text.
3. Replace the merged blob with one block per cell — precise bbox, `source:
   "surya-table"`, `class: "table"`, carrying `lang.<src>` — so each cell is an
   ordinary translatable block keyed by uid.

The translate stage then handles cells like any other block, and the existing
compositor renders them in place as a real grid (small per-cell text boxes — the
same path that already works for marker's native `TableCell` blocks). Numeric and
part-number cells classify `translate:false` and stay byte-identical.

**Sequencing — the re-translation is deferred and scheduled separately.** Cell
re-extraction is deterministic/GPU (no API tokens) and can run anytime. But the
recovered cells then need translation, which is LLM work; that is folded into the
scheduled translate run (the remaining full-book chunks + re-translation of the
~136 affected table pages), not run ad hoc.

## Consequences

### Positive

- Merged tables become legible translated grids instead of text walls, using the
  same deterministic-geometry / LLM-meaning split as the rest of the pipeline.
- Scoped to ~136 pages and to table regions only — far cheaper than re-OCRing
  everything; most tables (1688 cells) are already correct and untouched.
- The compositor needs no table-specific code: cells are just blocks.

### Negative

- A second table-recognition model load + inference on the affected pages.
- The ~136 affected pages (incl. some already translated in chunks 1–3) must be
  re-translated to fill the new cells — LLM cost, deferred to the scheduled run.
- Surya table-rec can mis-split dense or borderless tables; misfires fall to the
  ADR-203 interactive repair path.

### Neutral

- Adds `source: "surya-table"` to distinguish re-extracted cells from marker
  cells, parallel to `surya-figure` (ADR-201).

## Alternatives Considered

- **Leave the original scanned table un-overlaid.** Quick and safe (structure +
  part numbers stay readable), but leaves cells untranslated; rejected in favour of
  full translation quality, though it remains the graceful fallback for tables the
  recognizer can't split.
- **Best-effort reflow** of the blob with preserved line breaks. Cheap but still
  messy where the merge dropped row structure; rejected.
- **LLM parses the blob into cells.** Violates ADR-101 (geometry from OCR, not the
  model); rejected.
