---
name: doc-setup
description: Install or repair the Palimpsest toolchain — marker (via uv tool) + psutil, GPU torch (auto-detects AMD ROCm or NVIDIA CUDA and swaps it into marker's venv so OCR runs on the GPU), and the PyMuPDF/Pillow compositor venv. Use on a fresh machine, when doc-preflight reports RED/YELLOW, or when marker is stuck on CPU.
---

# doc-setup

Run the setup script (idempotent), then verify:

```bash
bash engine/scripts/setup.sh        # auto-detect GPU
# or
bash engine/scripts/setup.sh --cpu  # force CPU torch (no GPU / skip ROCm swap)

python3 engine/scripts/preflight.py # confirm GREEN
```

## What it does

1. **marker** — `uv tool install marker-pdf --with psutil` (psutil is a runtime dep
   uv otherwise omits; without it `marker_single` crashes on import).
2. **GPU torch** — detects ROCm (`rocm-smi`) or CUDA (`nvidia-smi`) and runs
   `uv pip install --python <marker-venv> --torch-backend=auto --reinstall-package torch "torch>=2.7,<3.0"`.
   The default marker install ships CUDA-only torch, so on AMD this swap is required
   to use the GPU (ADR-300). The wheel is large (~5–6 GB for ROCm); expect a wait.
3. **compositor venv** — creates `engine/.venv` and installs `pymupdf pillow`.

## Notes

- ROCm wheels bundle their own runtime libs and talk to the `amdgpu` kernel driver
  (`/dev/kfd`, `/dev/dri/renderD*`); they don't need the system ROCm userspace to match.
- Harmless `(null): No such file or directory` lines on stderr from HIP libs can be ignored.
- The marker venv is Python-version-specific; the system `python-pytorch-rocm` package
  (often a different Python) can't be reused directly — hence the in-venv install.
