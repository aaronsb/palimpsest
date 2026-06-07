---
status: Accepted
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-101, ADR-200]
---

# ADR-100: Extract IR boundary between deterministic OCR and LLM translation

## Context

Translating a scanned document has two very different kinds of work:

- **Extract** — render pages, run OCR/layout (marker/Surya) to get geometry,
  reading order, and source text. Deterministic, GPU-heavy, slow (~9 GPU-hours
  for a 1028-page book), and run *once* per source document.
- **Translate** — an LLM reads each page and produces translations +
  classifications. API-bound, parallel, and re-run *constantly*: to add a
  language, re-translate with a better model, fix QA findings, or retune the
  glossary.

If these two are coupled, every cheap re-translation drags the expensive OCR
along with it. We need a way to pay for extraction once and iterate on
translation freely.

## Decision

Separate the two stages with a **frozen, versioned intermediate representation —
the Extract IR** — and treat it as a hard contract.

- **Extract** writes `artifacts/` containing, per page, `p-NNNN.png`,
  `p-NNNN.overlay.png`, and `p-NNNN.page.json` (geometry + grid + source text,
  target languages empty), plus a `manifest.json` carrying `ir_version`,
  `doc_id`, `source_sha256`, page count, DPI, grid, and extractor provenance.
- The contract is `spec/schema.page.json` + `spec/schema.manifest.json`, both
  versioned by `ir_version`.
- **Translate** is a pure function of the IR + project config. It never writes
  into the IR; it emits translation layers keyed by the IR's stable UIDs.
- Translate refuses to run against a mismatched `ir_version`.

"Extract once, translate many times" is the governing principle.

## Consequences

### Positive

- The expensive OCR pass is cached forever; re-translation, new languages, and
  model upgrades cost nothing extra in extraction.
- Stages can evolve independently behind the schema.
- The IR is a durable, inspectable artifact and a natural resume/caching point;
  each page is independently addressable and re-runnable.

### Negative

- A schema to maintain and version; `ir_version` bumps require a migration story
  for already-extracted documents.
- Two-step runs are slightly more ceremony than a single monolithic script.

### Neutral

- The IR maps onto existing standards (hOCR/ALTO for boxes, XLIFF for the
  per-UID translation units), easing future interop.

## Alternatives Considered

- **Monolithic pipeline (OCR + translate in one pass).** Simplest to write, but
  re-running translation re-runs OCR — unacceptable given the cost asymmetry.
- **LLM does layout too (no OCR stage).** Rejected: VLMs are unreliable at
  precise geometry; see ADR-101. We want deterministic geometry as the
  foundation.
