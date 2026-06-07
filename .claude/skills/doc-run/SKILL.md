---
name: doc-run
description: Drive a Palimpsest project end-to-end — Extract (PDF→IR) → Translate (LLM workflow + glossary reconcile) → Compose (searchable + readable PDFs) → QA. Use to run the pipeline for a project in projects/<name>, or to run an individual stage. Knows the page-token convention, glossary write-back, and that a full-book translate is a large, billable fan-out to confirm and chunk.
---

# doc-run

Drives `projects/<name>` through the four stages. `engine/.venv/bin/python` runs the
Python steps; `marker_single` (its own ROCm venv) does OCR inside Extract. Always
`doc-preflight` first.

Let `P=projects/<name>`, `A=$P/artifacts`. Read langs/context/grid from `$P/config.json`.

## 1. Extract  (deterministic, GPU — run once)

```bash
engine/.venv/bin/python engine/scripts/extract.py $P          # whole doc
engine/.venv/bin/python engine/scripts/extract.py $P --pages 296-320   # a slice
```
Produces `$A/{pages,marker,json,overlay}` + `$A/manifest.json` (the Extract IR;
4-digit page ids `p-0001…`). If relaunching after a kill, `pkill -9 -f pdftoppm` first
(a stray render child collides — exit 144). Verify: `manifest.json` page_count matches.

## 2. Translate  (LLM fan-out + reconcile — billable, CONFIRM scope first)

Each page = one vision agent. **1028 pages ≈ 1028 agents — confirm with the user and
chunk** (≈100–200/batch) so the glossary accumulates and cost is staged. Generate the
page tokens from the page-json filenames, then run the workflow per chunk:

```bash
ls $A/json | sed -E 's/^p-([0-9]+)\.page\.json/\1/' | sort   # the 4-digit tokens
```
Invoke the workflow (name `doc-translate`, or scriptPath `engine/workflows/doc-translate.wf.js`)
with `args`:
```json
{ "root": "<abs A>", "pages": ["0001","0002", ...chunk...],
  "source_lang": "<sv>", "target_lang": "<en>",
  "domain_context": "<config.domain_context>",
  "glossary_path": "<abs A>/glossary.<target>.json" }
```
After each chunk, persist the reconciled glossary so the next chunk reuses it:
write the workflow result's `canonical` to `$A/glossary.<target>.json`. Agents write
`$A/llm/p-<token>.llm.json` themselves.

## 3. Apply + Compose  (deterministic)

```bash
for f in $A/llm/p-*.llm.json; do n=${f##*/p-}; n=${n%.llm.json};
  engine/.venv/bin/python engine/scripts/apply_translation.py $A/json/p-$n.page.json $f; done
engine/.venv/bin/python engine/scripts/compose_review.py $P/source/<pdf> $A/json $A/out/review.<lang>.pdf --lang <lang>
engine/.venv/bin/python engine/scripts/compose_A.py      $P/source/<pdf> $A/json $A/out/searchable.<lang>.pdf --lang <lang>
```
`compose_review` = readable (translation rendered in place); `compose_A` = searchable
(invisible layer over the scan). For huge books, compose in page ranges if memory is tight.

## 4. QA

```bash
engine/.venv/bin/python engine/scripts/qa.py $A/json
```
Deterministic checks: leftover source-language chars, number/part-number drift, UID
uniqueness. Pair with a cheap-model visual pass on a sample of composed pages.

## Adding a language later

Re-run only stages 2–3 with a new `target_lang` against the SAME IR — no re-extract.
