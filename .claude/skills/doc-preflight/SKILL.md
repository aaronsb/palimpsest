---
name: doc-preflight
description: Check whether this machine can run the Palimpsest document pipeline — GPU/ROCm vs CPU torch backend in marker's venv, marker/Surya importability, the PyMuPDF compositor venv, system tools (qpdf, pdftoppm), and disk; prints a red/yellow/green verdict with a runtime estimate. Use before an extract run, after changing the environment, or when diagnosing "marker is slow / on CPU".
---

# doc-preflight

Run the capability check and interpret it:

```bash
python3 engine/scripts/preflight.py [--pages N]
```

`--pages N` scales the disk/runtime estimate (default 1028).

## Reading the verdict

- **GREEN** — everything ready; proceed.
- **YELLOW** — runnable but suboptimal. The usual cause is `marker:torch backend=cpu`
  on a machine with a GPU → OCR will be ~2–3× slower. Fix with the `doc-setup` skill.
- **RED** — a `BAD` item blocks running. Run the `doc-setup` skill, then re-check.

## What each row means

- `marker:torch` — the torch build inside marker's uv venv. `backend=rocm|cuda gpu=yes`
  is what you want. `backend=cpu` on an AMD/NVIDIA box means the GPU isn't being used
  (the default marker install ships CUDA-only torch — see ADR-300).
- `marker:imports` — marker + surya + psutil import cleanly (psutil is a runtime dep uv may omit).
- `engine:venv` — the PyMuPDF/Pillow compositor venv at `engine/.venv`.

The runtime estimate uses ~14 s/page on ROCm, ~10 s/page on CUDA, ~32 s/page on CPU.
