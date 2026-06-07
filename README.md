# Palimpsest

> *palimpsest* (PAL-imp-sest) — a manuscript page scraped clean and written over, the original still faint beneath.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/aaronsb/palimpsest/actions/workflows/ci.yml/badge.svg)](https://github.com/aaronsb/palimpsest/actions/workflows/ci.yml)

Palimpsest turns a **scanned PDF in one language** into a **searchable, layout-preserving, multilingual PDF** — by scraping the original text and writing translations back in its place, over the original diagrams.

It was built to translate a 1028-page Swedish military vehicle workshop manual into English, but nothing in the engine is specific to that document.

## How it works

Three stages separated by a hard, versioned boundary — **extract once, translate many times**:

```
A. EXTRACT   (deterministic, GPU)   PDF ─► Extract IR   (geometry + grid + source text, frozen)
B. TRANSLATE (LLM, parallel)        IR  ─► translation layers   (per language, keyed by stable UID)
C. COMPOSE   (deterministic)        IR + layers ─► output PDF
                                    • Mode A: invisible text layer over the scan (searchable)
                                    • Mode B: translated text rendered in place (readable)
```

The OCR engine ([marker](https://github.com/datalab-to/marker)/Surya) owns **geometry**; the LLM owns **meaning** (translation + classification) and recovers text the OCR missed (diagram labels, faint headers); the compositors are dumb and deterministic. A painted coordinate grid gives the LLM a *vocabulary* to point at regions — it never emits raw coordinates.

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full flow and [`spec/`](spec/) for the data contracts.

## Layout

```
engine/          # document-agnostic engine
  scripts/       # extract → overlay → apply → compose → qa
  workflows/     # doc-translate: the LLM translate+reconcile fan-out (Claude Code Workflow)
spec/            # schema.page.json, schema.manifest.json — the Extract IR contract
docs/            # PIPELINE.md + architecture/ (ADRs)
.claude/         # skills (preflight, setup, run) + workflows
projects/<name>/ # per-document: config.json (langs, domain context, glossary seed)
  source/        # the input PDF        (gitignored)
  artifacts/     # all generated output (gitignored)
```

Source documents and artifacts are **never committed** — the engine is the product, documents are inputs.

## Status

Proof of concept complete: a 25-page slice translated Swedish→English end-to-end (282-term reconciled glossary, searchable + readable PDFs). Known gaps tracked as issues: diagram leader-label anchoring (Mode B), dense-table translation policy. Next: AMD ROCm acceleration, then the full-book extract.

## License

MIT © Aaron Bockelie
