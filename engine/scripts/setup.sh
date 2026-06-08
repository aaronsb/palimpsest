#!/usr/bin/env bash
# Palimpsest environment setup — installs/repairs the OCR + compositor toolchain.
# Idempotent. Detects a GPU and installs the matching torch into marker's venv so
# OCR runs on the GPU; otherwise leaves the default CPU torch in place.
#
# Usage: setup.sh           (auto-detect GPU)
#        setup.sh --cpu     (force CPU torch, skip GPU swap)
#        setup.sh --rocm    (force AMD ROCm torch)
#        setup.sh --cuda    (force NVIDIA CUDA torch)
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
MARKER_PY="$HOME/.local/share/uv/tools/marker-pdf/bin/python"

echo "== Palimpsest setup =="
command -v uv >/dev/null || { echo "ERROR: 'uv' not found on PATH. Install uv first: https://docs.astral.sh/uv/"; exit 1; }

# 1) marker (via uv tool) + psutil (a marker runtime dep uv may omit)
if ! command -v marker_single >/dev/null; then
  echo "-- installing marker-pdf via uv tool"
  uv tool install marker-pdf --with psutil || { echo "ERROR: marker-pdf install failed"; exit 1; }
else
  echo "-- marker present; ensuring psutil"
  uv tool install marker-pdf --with psutil >/dev/null 2>&1
fi
[ -x "$MARKER_PY" ] || { echo "ERROR: marker venv python not found at $MARKER_PY after install"; exit 1; }

# 2) GPU torch backend for marker's venv
detect_gpu() {
  if command -v rocm-smi >/dev/null && rocm-smi --showid >/dev/null 2>&1; then echo rocm; return; fi
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then echo cuda; return; fi
  # ROCm wheels need only the amdgpu kernel driver, not rocm-smi userspace (ADR-300)
  if [ -e /dev/kfd ] && ls /dev/dri/renderD* >/dev/null 2>&1; then echo rocm; return; fi
  echo cpu
}
case "${1:-}" in
  --cpu)  GPU=cpu ;;
  --rocm) GPU=rocm ;;
  --cuda) GPU=cuda ;;
  "")     GPU="$(detect_gpu)" ;;
  *)      echo "ERROR: unknown arg '$1' (use --cpu|--rocm|--cuda)"; exit 1 ;;
esac
echo "-- GPU backend: $GPU"
if [ "$GPU" != "cpu" ]; then
  echo "-- installing $GPU torch into marker venv (large download)"
  uv pip install --python "$MARKER_PY" --torch-backend=auto --reinstall-package torch "torch>=2.7,<3.0" \
    || { echo "ERROR: $GPU torch install failed — marker stays on its current (likely CPU) torch. Re-run, or use --cpu to accept CPU."; exit 1; }
fi
echo -n "-- marker torch: "
"$MARKER_PY" -c "import torch;print(torch.__version__,'gpu',torch.cuda.is_available())" 2>/dev/null \
  || { echo "ERROR: torch import failed in marker venv"; exit 1; }

# 3) compositor venv (PyMuPDF + Pillow + numpy)
if [ ! -x "$REPO/engine/.venv/bin/python" ]; then
  echo "-- creating engine venv"
  uv venv "$REPO/engine/.venv" --python 3.12 || { echo "ERROR: engine venv create failed"; exit 1; }
fi
uv pip install --python "$REPO/engine/.venv/bin/python" pymupdf pillow numpy >/dev/null \
  || { echo "ERROR: pymupdf/pillow/numpy install failed"; exit 1; }
echo -n "-- engine venv: "
"$REPO/engine/.venv/bin/python" -c "import fitz,PIL,numpy;print('ok')"

echo "== done. Verify: python3 engine/scripts/preflight.py"
