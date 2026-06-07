#!/usr/bin/env bash
# Palimpsest environment setup — installs/repairs the OCR + compositor toolchain.
# Idempotent. Detects an AMD GPU and installs ROCm torch into marker's venv so OCR
# runs on the GPU; otherwise leaves the default CPU torch in place.
#
# Usage: setup.sh        (auto-detect)
#        setup.sh --cpu  (force CPU torch, skip ROCm swap)
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
MARKER_PY="$HOME/.local/share/uv/tools/marker-pdf/bin/python"
FORCE_CPU="${1:-}"

echo "== Palimpsest setup =="

# 1) marker (via uv tool) + psutil (a marker runtime dep uv may omit)
if ! command -v marker_single >/dev/null; then
  echo "-- installing marker-pdf via uv tool"
  uv tool install marker-pdf --with psutil
else
  echo "-- marker present; ensuring psutil"
  uv tool install marker-pdf --with psutil >/dev/null 2>&1
fi

# 2) GPU torch backend for marker's venv
detect_gpu() {
  command -v rocm-smi >/dev/null && rocm-smi --showid >/dev/null 2>&1 && { echo rocm; return; }
  command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1 && { echo cuda; return; }
  echo cpu
}
GPU="$([ "$FORCE_CPU" = "--cpu" ] && echo cpu || detect_gpu)"
echo "-- GPU backend detected: $GPU"
if [ "$GPU" != "cpu" ]; then
  echo "-- installing $GPU torch into marker venv (large download)"
  uv pip install --python "$MARKER_PY" --torch-backend=auto --reinstall-package torch "torch>=2.7,<3.0"
fi
echo -n "-- marker torch: "
"$MARKER_PY" -c "import torch;print(torch.__version__,'gpu',torch.cuda.is_available())" 2>/dev/null

# 3) compositor venv (PyMuPDF + Pillow)
if [ ! -x "$REPO/engine/.venv/bin/python" ]; then
  echo "-- creating engine venv"
  uv venv "$REPO/engine/.venv" --python 3.12
fi
uv pip install --python "$REPO/engine/.venv/bin/python" pymupdf pillow >/dev/null
echo -n "-- engine venv: "
"$REPO/engine/.venv/bin/python" -c "import fitz,PIL;print('ok')"

echo "== done. Run preflight to verify: engine/.venv/bin/python engine/scripts/preflight.py"
