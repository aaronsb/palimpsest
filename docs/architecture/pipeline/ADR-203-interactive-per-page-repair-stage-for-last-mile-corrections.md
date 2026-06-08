---
status: Accepted
date: 2026-06-08
deciders:
  - aaronsb
related: [ADR-100, ADR-101, ADR-200, ADR-202]
---

# ADR-203: Interactive per-page repair stage for last-mile corrections

## Context

The automated passes — the batched translate workflow (ADR-100/101) and the
deterministic compositors (ADR-200/202) — get the large majority of pages right
at scale. But a representative 12-page trial surfaced a residual class of
per-page defects that the scaled passes do not self-correct:

- **Block placement.** A translated block occasionally sits where its OCR box was,
  but the English text reflows to a different length/shape than the source, so the
  masked-and-rendered result reads slightly misplaced or cramped.
- **Upstream mis-segmentation.** marker sometimes merges a structured region into
  one block — e.g. an entire electrical parts table collapsed into a single
  ~3 KB "paragraph" — which then translates as one unhelpful blob instead of a
  legible table. The geometry is wrong at the source, so no amount of translation
  quality fixes it.
- **Long-tail oddities.** Phantom empty blocks on blank pages, a caption the model
  classed as prose, a label whose box overlaps a leader line, etc.

These are last-mile problems: cheap for a human to *spot* and *describe*, and cheap
to fix deterministically once described, but expensive and unreliable to catch with
another automated pass. ADR-202 already records an *automated* vision trap-verify
polish pass as **deferred** for exactly this reason — it is costly per page and
still imperfect. We need a complementary, human-driven path for the pages a person
flags on review, without re-running anything at book scale.

The Extract IR boundary (ADR-100) already makes this safe: every page is an
independent, editable JSON record, and composition is deterministic, so a single
page can be corrected and recomposed in isolation without touching the rest of the
book.

## Decision

Add an explicit **interactive per-page repair stage** as the final, optional step
of the flow, and **retain all artifacts** (the IR + `llm/` patches + composed
output, version-controlled per the artifacts submodule) specifically so this stage
is possible after the fact.

The stage is **conversational, not a workflow.** The human reviews the composed
output, **redlines** specific pages (a page list plus a note on what's wrong), and
works directly with the agent — one page at a time — to apply a targeted fix and
recompose just that page. There is no fan-out, no glossary reconcile, no batch; the
unit of work is one page and one human intent.

**Repair operations** act on the durable artifacts, in order of preference for the
least-invasive fix:

| Symptom | Repair |
|---|---|
| Wrong translation / class / `translate` flag | Edit that block in `json/p-NN.page.json` (or the `llm/` patch), recompose the page |
| Text misplaced / cramped | Adjust the block's compose treatment (font clamp, grow-direction, trap) or its `bbox_pt`, recompose |
| One block should be many (merged table/list) | Re-segment in the page JSON — split the block into rows/cells with their own boxes — then re-translate just those, recompose |
| Mask bleed / residual source ink | Tune trap for that page (ADR-202 `--trap-cap`/fixed), recompose |

The boundary with the automated stages is explicit: **scale and breadth → workflow**
(parallel fan-out, glossary consistency); **last-mile and depth → interactive**
(surgical, single page, human-judged). This stage is the human realization of the
"polish" that ADR-202 §2 deferred as automation.

**Recompose scope** is always minimal: a single page or a small explicit range via
`compose_review.py` over a temp/filtered JSON dir, so a repair never re-renders the
book and the change is trivially reviewable (one page diff in the artifacts repo).

## Consequences

### Positive

- The last-mile defects that automation can't reliably catch get fixed by the
  cheapest competent reviewer (a human eye + a deterministic recompose), with no
  book-scale recompute.
- Artifacts become first-class, durable, editable state — repairs are normal IR
  edits, diffable and revertible in the artifacts repo, not a special mode.
- Keeps the expensive automated polish pass (ADR-202 §2) deferred/unbuilt: the
  human covers the same need until/unless volume justifies automating it.
- Per-page isolation (ADR-100) means a repair can never regress another page.

### Negative

- Manual effort scales with the number of flagged pages; on a very large book the
  reviewer is the bottleneck for the long tail.
- Re-segmenting a marker-merged region by hand is fiddly (defining new boxes by
  grid/points), though bounded to the few pages where it matters.
- Repairs live in the (gitignored-from-the-public-engine) artifacts repo, so the
  fixes are not portable with the engine — by design, but worth stating.

### Neutral

- Encourages a lightweight **redline format** (page + note) as the hand-off from
  human review to repair; no tooling required beyond conversation, but a simple
  list keeps a record of what was touched and why.
- Suggests a future convenience: a `compose_review.py --pages <list>` filter and/or
  a "recompose these pages" helper to make the recompose step one command.

## Alternatives Considered

- **Automated vision repair pass for everything (ADR-202 §2).** Rejected as the
  default — costly per page, still imperfect, and unnecessary when a human can spot
  the rare failures directly. Kept deferred; this ADR is its human complement.
- **Re-run the whole translate/compose with a better prompt.** Rejected for
  last-mile fixes — it re-spends tokens on the 95% that were already correct and
  isn't guaranteed to fix the specific page; the prompt tweak belongs upstream when
  a defect is *systematic*, not per-page.
- **Fix defects only at the source (marker segmentation).** Not always possible —
  some failures are inherent to OCR layout analysis; correcting in the IR is the
  pragmatic place. Systematic upstream fixes still happen when warranted.
- **Treat the composed PDF as final / accept the defects.** Rejected — the goal is
  a genuinely readable human artifact; the long tail is exactly what makes it feel
  finished.
