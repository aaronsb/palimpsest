# Contributing to Palimpsest

Thanks for your interest. Palimpsest is an engine for translating and
reconstructing scanned documents into searchable, layout-preserving,
multilingual PDFs.

## Ground rules

- **Never commit source documents or generated artifacts.** They are gitignored
  (`*.pdf`, `projects/*/source/`, `projects/*/artifacts/`). The engine is the
  product; documents are inputs.
- **The engine is document-agnostic.** Anything document-specific (languages,
  domain context, glossary seeds) belongs in a project's `config.json`, not in
  engine code.
- **Respect the stage boundary.** The deterministic Extract pass and the LLM
  Translate pass are separated by a versioned intermediate representation (the
  Extract IR). Don't couple them. See `docs/PIPELINE.md` and the ADRs.

## Workflow

1. Branch (`feature/...`, `fix/...`, `adr-NNN-...`).
2. Make atomic, conventionally-formatted commits (`feat(engine): ...`).
3. Open a PR — even solo. Describe the *why*.
4. Architectural decisions get an ADR (`docs/scripts/adr new <domain> "<title>"`).

## Code

- Python: ruff-clean, Google-style docstrings on public functions.
- Keep scripts parameterized (paths/langs via args or config, never hardcoded).
