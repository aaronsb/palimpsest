---
status: Accepted
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-101, ADR-100, ADR-200]
---

# ADR-201: In-figure text detection for precise label geometry

## Context

marker's layout step collapses each exploded-view diagram into a single
`Picture` block and does not OCR the leader-labels inside it (verified: a
fuel-system figure yields one `Picture` bbox + a caption, no label boxes). Those
labels (`Luftintag`, `Tryckregulator`, …) therefore had no geometry.

The first approach had the LLM *recover* them by reading a painted coordinate
grid and returning a grid cell. But the grid is 24×34 over A4 → ~25 pt cells,
far larger than a label, so placement was coarse and labels rendered offset from
(or overlapping) the originals. Per ADR-101 the LLM should not be the source of
geometry; the grid is a vocabulary, not a measuring tape.

## Decision

Add a deterministic **in-figure detection pass** to the Extract stage
(`engine/scripts/detect_in_figures.py`): for each page, crop marker's figure
regions from the upright render and run **Surya detection + recognition** on just
those crops. Every found line becomes a block with a **precise OCR bbox** + source
text, tagged `source: "surya-figure"`, `class: "label"`. Low-confidence /
single-char / punctuation-only hits are filtered (default `min_conf 0.7`).

The translate stage then translates these like any other block, so labels get
their real geometry; the grid-recovery path is demoted to a rare fallback for
text with no box at all (e.g. a missed header). Detection runs in the marker venv
(Surya + ROCm torch), invoked by `extract.py` after `build_page_json` and before
overlay generation, so the boxes appear on the gridded image the LLM sees.

## Consequences

### Positive

- Labels are placed precisely over the originals (validated on the fuel-system
  page: labels boxed at 0.92–0.99 confidence, English rendered in place cleanly).
- Geometry stays deterministic and OCR-sourced (ADR-101); the LLM only translates.
- Scoped to figure crops, so it's far cheaper than a full second-pass OCR.

### Negative

- A second OCR model load + inference per extract (figure crops only — modest).
- Surya can emit noise on dense hatching; mitigated by the confidence/length filter.
- Re-running detection on already-translated pages requires re-translation to pick
  up the new label blocks (and to drop stale grid-recovered ones).

### Neutral

- Adds a `source` field to blocks distinguishing marker vs detected geometry.

## Alternatives Considered

- **Finer grid + LLM recovery.** Rejected — the limiter is the VLM's spatial
  estimation, not cell size; denser grids are also harder to read and clutter the
  overlay.
- **Ink-snap refinement** (tighten coarse boxes to dark pixels via image ops).
  Cheaper, but risks snapping onto leader lines; kept as a possible later refiner.
- **Full-page second-pass OCR.** Most complete but roughly doubles extract cost;
  figure-only cropping gets the missing text for a fraction of the compute.
