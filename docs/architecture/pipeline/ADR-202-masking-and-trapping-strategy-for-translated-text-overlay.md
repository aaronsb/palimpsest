---
status: Proposed
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-200, ADR-201]
---

# ADR-202: Masking and trapping strategy for translated-text overlay

## Context

The readable compositor (Mode B-lite, ADR-200) covers each source-language text
region with a white mask and renders the translation in its place. The mask must
**fully cover** the original ink (otherwise Swedish fragments — descenders,
anti-aliased edges, glyphs that spill past the OCR box — peek out) while **not
covering** the surrounding diagram (otherwise it paints white notches over leader
lines and drawing strokes). A single global margin can't satisfy both: too small
leaks fragments, too large eats the diagram. Borrowing the print term, the mask
needs **trapping** — but ideally trapping that adapts to the actual ink.

## Decision

**1. Content-aware auto-trap (default masking).** Instead of a fixed margin, grow
each side of the mask outward one pixel-line at a time *while that line still
contains ink*, stopping at the first clean (whitespace) line, hard-capped at
`--trap-cap` (default 6 pt). The whitespace-stop is what makes it safe: the gap
between a label and its leader line halts growth before it reaches the line, so
the mask hugs the glyphs without bleeding onto the diagram. Implemented in
`compose_review.py` (`--auto-trap`), using a per-page ink array (numpy). A fixed
margin (`--trap-x/--trap-y`) remains as a deterministic fallback.

- **Bounded growth is mandatory** — the cap prevents a label that physically
  touches a stroke (no whitespace gap) from running away; worst case it grows by
  the cap and no further.

**2. Optional vision trap-verification polish pass (DEFERRED — build only if
needed).** After trapping, render each page with the trap regions drawn as
*translucent* red over the original scan, numbered 1..N. A vision model reviews it
and returns, per box, one of: `ok`, `under` (source ink visible outside the box),
`over` (box covers diagram strokes). A deterministic pass then adjusts only the
flagged boxes (grow `under`, shrink `over`) and re-composes. Translucency is
required so the model can see *both* failure modes; opaque boxes hide leaks.

   - **Trigger condition (when to build it):** only if review of auto-trap output
     across a representative page set shows residual under/over-trap that the
     cap+whitespace heuristic can't fix cheaply. If auto-trap is clean, this pass
     is unnecessary cost and we do not build it.
   - **Cost:** ~one extra vision call per page — comparable to the translate pass,
     so non-trivial at 1028 pages; reserve for a final polish, possibly only on
     pages flagged by deterministic heuristics (e.g. detected ink remaining inside
     a mask after compositing).

## Consequences

### Positive

- Auto-trap covers fragments where a fixed margin is too small and avoids bleeding
  where it'd be too big — per-block, no global compromise.
- The deferred polish pass has a recorded design and a clear build trigger, so it
  can be added later without re-deliberation, and isn't paid for unless warranted.

### Negative

- Auto-trap adds per-page image work (numpy ink scan) — negligible.
- Residual failure mode (text touching a stroke) remains, bounded by the cap;
  the polish pass exists to catch exactly these if they prove common.
- The polish pass, if built, roughly doubles per-page model cost on the pages it runs.

### Neutral

- Adds `numpy` as a compositor dependency (record in setup.sh).

## Alternatives Considered

- **Fixed margin only.** Simple, deterministic, but cannot simultaneously cover
  spill and spare nearby strokes; kept as fallback, not default.
- **Connected-component ink bbox** (`PIL.getbbox` per component, keep components
  centred in the box). Slightly more robust to diagonal overhang but more code;
  grow-until-clean is simpler and sufficient. Possible future refinement.
- **Always run the vision polish pass.** Rejected as default — unnecessary cost
  when auto-trap already produces clean output; gated behind the trigger condition.
