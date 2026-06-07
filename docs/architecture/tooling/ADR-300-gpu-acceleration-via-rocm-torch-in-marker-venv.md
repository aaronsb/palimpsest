---
status: Accepted
date: 2026-06-07
deciders:
  - aaronsb
related: [ADR-100]
---

# ADR-300: GPU acceleration via ROCm torch in marker's venv

## Context

The Extract stage (ADR-100) runs marker/Surya, which is torch-based. marker is
installed as a uv tool, and its bundled torch is a **CUDA** build (`+cuXXX`). On
an AMD machine (this one: Radeon RX 7900 XTX, gfx1100, ROCm 7.2) that torch
cannot see the GPU, so OCR falls back to CPU — ~32 s/page, ~9 h for the
1028-page book, and it pegs all cores.

The system already runs torch on ROCm, but as the Arch package
`python-pytorch-opt-rocm` built for a different Python than marker's venv
(3.14 vs 3.12), so it can't be reused by ABI. We need GPU OCR without rebuilding
marker from scratch or maintaining a fork.

## Decision

Swap marker's venv torch for a **ROCm build** in place, using uv's torch backend
detection:

```bash
uv pip install --python ~/.local/share/uv/tools/marker-pdf/bin/python \
  --torch-backend=auto --reinstall-package torch "torch>=2.7,<3.0"
```

- `--torch-backend=auto` detects the GPU and selects the matching PyTorch index.
- `--reinstall-package torch` forces the swap even though the existing CUDA torch
  already satisfies the version constraint (otherwise uv no-ops).
- `>=2.7,<3.0` stays within marker/surya's pin.
- `psutil` must also be present (`uv tool install marker-pdf --with psutil`) — a
  marker runtime dep uv otherwise omits.

This is encoded in `engine/scripts/setup.sh` (auto-detects ROCm/CUDA/CPU) and
checked by `engine/scripts/preflight.py`. ROCm wheels bundle their own runtime
libs and talk to the `amdgpu` kernel driver, so the system ROCm userspace version
need not match the wheel's.

## Consequences

### Positive

- OCR runs on the GPU: measured ~13.7 s/page (≈3.9 h for 1028 pp) vs ~32 s/page
  on CPU — ~2.3× faster, and it frees the CPU/keeps the box cool.
- Repeatable via `setup.sh`; verifiable via `preflight.py`; portable to NVIDIA
  (same flags select a CUDA index) or CPU (`--cpu`).

### Negative

- Large download (~5–6 GB ROCm wheel). Speedup is ~2.3×, not 5–10×, because
  marker has CPU-bound stages (PDF parsing, layout post-processing, IO) that the
  GPU doesn't accelerate.
- Couples to uv's torch-backend detection and the marker venv's interpreter path.

### Neutral

- Harmless `(null): No such file or directory` HIP stderr noise appears on import.

## Alternatives Considered

- **Reuse the system Arch ROCm torch.** Rejected — built for a different Python
  than marker's venv (ABI incompatible).
- **Rebuild marker against ROCm from source / fork it.** Rejected — heavy and
  hard to maintain vs a one-line in-venv reinstall.
- **Stay on CPU.** Rejected — ~9 h per extract and full-core load make iteration
  painful, though `--cpu` remains the documented fallback.
