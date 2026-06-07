---
status: Accepted
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-100, ADR-101]
---

# ADR-200: Two compose modes — searchable layer, then visual reproduction

## Context

Once a page has translations keyed to geometry, there are two distinct things a
reader might want:

1. A document that *looks like the original scan* but is **searchable/queryable**
   in the target language (and the source).
2. A document they can actually **read in the target language**, with the
   translation rendered in place of the original text.

These have very different difficulty. (1) is the standard OCR "sandwich" — an
invisible text layer behind the scan — with no text-fitting or inpainting
problem. (2) requires covering the source text, fitting translated text (which
changes length) into tight technical layouts, and anchoring diagram leader-labels
to their leader lines.

## Decision

Support **both modes from one data model**, and build them in order:

- **Mode A (searchable) — build first.** Keep the scan; add an invisible,
  per-language text layer positioned at each block's bbox. Part numbers are
  included verbatim so they remain searchable. No fitting problem. Delivers
  ~80% of the value (searchable, queryable, multilingual) at ~20% of the effort.
- **Mode B (visual reproduction) — later, same JSON.** A different deterministic
  compositor whites out / inpaints the source text regions and renders the
  target text in place (shrink-to-fit, wrap; leader-labels anchored).

Switching modes is a **compositor swap, not a re-processing** of the document.
An interim "review proof" compositor (Mode B-lite: white-box text regions + render
target text, diagrams left showing) exists for human review while full Mode B is
developed.

## Consequences

### Positive

- Fast path to a useful, searchable artifact; Mode B is incremental, not a
  prerequisite.
- One translation data set serves every output form and language.

### Negative

- Full Mode B carries the hard problems (text fitting, inpainting, leader-label
  anchoring) — explicitly deferred, tracked as issues.

### Neutral

- Mode A equals `ocrmypdf`-style sandwiching; interoperable with standard PDF
  text-layer expectations.

## Alternatives Considered

- **Only Mode B (visual reproduction).** Rejected as the first deliverable —
  highest-risk work up front delays any usable output.
- **Only Mode A (searchable).** Insufficient — a human can't *read* the
  translation, only search it; the project explicitly wants readable output.
