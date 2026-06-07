export const meta = {
  name: 'doc-translate',
  description: 'Translate+classify prepped document pages (vision fan-out) then reconcile a canonical glossary',
  phases: [
    { title: 'Translate', detail: 'one vision agent per page: reads overlay+page.json, writes llm patch, returns glossary fragment' },
    { title: 'Reconcile', detail: 'one agent merges all glossary fragments into a canonical source→target map + conflict list' },
  ],
}

// args (passed by the run skill, derived from projects/<name>/config.json):
//   root           artifacts dir holding overlay/, json/, llm/   (required)
//   pages          array of page tokens matching p-<token>.png    (required)
//   source_lang    e.g. "sv"                                      (required)
//   target_lang    e.g. "en"                                      (required)
//   domain_context one-paragraph translation guidance             (required)
//   glossary_path  path to a glossary json to reuse/extend        (optional)
let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { /* leave as-is */ } }
const ROOT = A.root
// pages: explicit token list, OR a range {first,last,pad} to generate them
let PAGES = A.pages || []
if (!PAGES.length && A.range) {
  const pad = A.range.pad || 4
  for (let i = A.range.first; i <= A.range.last; i++) PAGES.push(String(i).padStart(pad, '0'))
}
const SRC = A.source_lang || 'sv'
const TGT = A.target_lang || 'en'
const CTX = A.domain_context || ''
const GLOSS = A.glossary_path || `${ROOT}/glossary.json`
const MODEL = A.model  // undefined => inherit main-loop model; 'sonnet'|'haiku'|'opus' to pin
if (!ROOT || !PAGES.length) throw new Error('doc-translate: args.root and args.pages are required')

const TRANSLATE_SCHEMA = {
  type: 'object',
  required: ['page', 'n_blocks', 'n_recovered', 'glossary'],
  properties: {
    page: { type: 'string' },
    n_blocks: { type: 'integer' },
    n_recovered: { type: 'integer' },
    glossary: { type: 'object', additionalProperties: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const RECON_SCHEMA = {
  type: 'object',
  required: ['canonical', 'conflicts'],
  properties: {
    canonical: { type: 'object', additionalProperties: { type: 'string' } },
    conflicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          src: { type: 'string' },
          options: { type: 'array', items: { type: 'string' } },
          chosen: { type: 'string' },
        },
      },
    },
  },
}

const translatePrompt = (n) => `You are the translate+classify stage of the Palimpsest document pipeline. Translate ${SRC} → ${TGT}.

## Document context
${CTX}

## Read these files
1. Gridded overlay image (faint coord grid, numbered+colored boxes): ${ROOT}/overlay/p-${n}.grid.png
2. Source blocks (uid, order, class guess, grid_ref, source text in lang.${SRC}): ${ROOT}/json/p-${n}.page.json
3. Running glossary (if present, REUSE these term choices for consistency): ${GLOSS}

Grid: columns numbered along the top, rows down the left. Each box is labeled with its \`order\`. Use grid coordinates ONLY to locate text the OCR missed.

## For EVERY block in the source JSON decide
- class ∈ {prose, heading, step, warning, caption, label, part_number, identifier, header_band, table, other}
  - step = numbered procedure line (keep the leading number); caption = figure caption; warning = warning/note callout; header_band = page header line → translate=false; part_number/identifier = tool/part/drawing numbers → translate=false, byte-identical.
  - table = a cell in a data table. TRANSLATE descriptive cells; keep numeric/part-number cells verbatim. Never leave a table cell's ${TGT} empty.
- translate: false for header_band/part_number/identifier; true otherwise.
- ${TGT}: the translation. For translate=false, COPY the source verbatim into the ${TGT} field (never leave it empty). Preserve ALL digits exactly.

## Recover text the OCR MISSED
Diagram leader-labels and (on some pages) the header band are often absent from the source blocks. Read each off the painted grid and emit a \`recovered\` entry: {grid_ref:{c0,r0,c1,r1}, class, ${SRC}, ${TGT}}.

## Write the result file (this is the real output)
Write ONLY this JSON to ${ROOT}/llm/p-${n}.llm.json :
{ "blocks":[{"uid","class","translate","${TGT}"},...], "recovered":[{"grid_ref":{c0,r0,c1,r1},"class","${SRC}","${TGT}"},...], "glossary":{"srcterm":"tgtterm",...} }
Include a blocks entry for EVERY uid in the source.

## Return (structured)
Return: page="${n}", n_blocks, n_recovered, glossary (the source→target map you used), and a one-line notes string.`

phase('Translate')
const results = await parallel(
  PAGES.map((n) => () =>
    agent(translatePrompt(n), {
      label: `translate:p-${n}`,
      phase: 'Translate',
      schema: TRANSLATE_SCHEMA,
      agentType: 'general-purpose',
      model: MODEL,
    })
  )
)

const ok = results.filter(Boolean)
const fragments = ok.map((r) => ({ page: r.page, glossary: r.glossary }))
log(`translated ${ok.length}/${PAGES.length} pages; ${fragments.length} glossary fragments`)

phase('Reconcile')
const canonical = await agent(
  `You are reconciling terminology across a ${SRC}→${TGT} technical translation.
Document context: ${CTX}

Per-page glossary fragments (${SRC}→${TGT}) from ${fragments.length} pages:
${JSON.stringify(fragments, null, 2)}

Produce ONE canonical ${SRC}→${TGT} glossary: for each source term pick the single best target term, normalizing inconsistencies. Where pages disagreed, record a conflict {src, options:[...], chosen}.
Return {canonical:{src:tgt,...}, conflicts:[...]}.`,
  { label: 'reconcile-glossary', phase: 'Reconcile', schema: RECON_SCHEMA, agentType: 'general-purpose', model: MODEL }
)

return {
  pages_done: ok.map((r) => r.page),
  pages_failed: PAGES.filter((n) => !ok.find((r) => r.page === n)),
  glossary_terms: Object.keys(canonical?.canonical || {}).length,
  conflicts: canonical?.conflicts || [],
  canonical: canonical?.canonical || {},
}
