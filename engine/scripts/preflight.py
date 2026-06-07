#!/usr/bin/env python3
"""Palimpsest preflight — does this machine have what the pipeline needs?

Checks the OCR toolchain (marker + its torch backend + GPU), the compositor
venv (PyMuPDF), system tools (qpdf, pdftoppm), and disk; prints a red/yellow/
green report with a rough runtime estimate. Stdlib only; shells out to probe
the marker venv. Usage: preflight.py [--pages N]
"""
import os
import shutil
import subprocess
import sys

MARKER_PY = os.path.expanduser("~/.local/share/uv/tools/marker-pdf/bin/python")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE_PY = os.path.join(REPO, "engine", ".venv", "bin", "python")

OK, WARN, BAD = "OK ", "WARN", "BAD "
rows = []


def add(level, name, detail):
    rows.append((level, name, detail))


def probe(py, code):
    """Return (rc, stdout, stderr). stdout is parsed; stderr only shown on error
    (ROCm/HIP libs emit harmless '(null): No such file' noise to stderr)."""
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def main():
    pages = 1028
    if "--pages" in sys.argv:
        try:
            pages = int(sys.argv[sys.argv.index("--pages") + 1])
        except (IndexError, ValueError):
            print("usage: preflight.py [--pages N]   (N = integer page count)")
            sys.exit(2)

    # system tools
    for tool in ("qpdf", "pdftoppm", "marker_single"):
        add(OK if shutil.which(tool) else BAD, f"tool:{tool}",
            shutil.which(tool) or "NOT FOUND")

    # marker venv torch + GPU backend
    device = "cpu"
    if os.path.exists(MARKER_PY):
        rc, out, err = probe(MARKER_PY,
                             "import torch;print(torch.__version__, torch.version.hip, "
                             "torch.cuda.is_available(), torch.cuda.get_device_name(0) "
                             "if torch.cuda.is_available() else 'none')")
        if rc == 0 and out:
            ver, hip, avail, name = (out.split(None, 3) + ["", "", "", ""])[:4]
            gpu = avail == "True"
            device = ("rocm" if hip not in ("None", "") else "cuda") if gpu else "cpu"
            add(OK if gpu else WARN, "marker:torch",
                f"{ver} backend={device} gpu={'yes ('+name+')' if gpu else 'NO — CPU only'}")
        else:
            add(BAD, "marker:torch", (err or "probe failed").splitlines()[-1][:80])
        rc, out, err = probe(MARKER_PY, "import marker,surya,psutil;print('ok')")
        add(OK if rc == 0 else BAD, "marker:imports", "ok" if rc == 0 else (err or out)[:80])
    else:
        add(BAD, "marker:venv", f"missing {MARKER_PY} — run doc-setup")

    # compositor venv
    if os.path.exists(ENGINE_PY):
        rc, out, err = probe(ENGINE_PY, "import fitz,PIL;print('pymupdf',fitz.VersionBind)")
        add(OK if rc == 0 else BAD, "engine:venv", out if rc == 0 else (err or out)[:80])
    else:
        add(BAD, "engine:venv", f"missing {ENGINE_PY} — run doc-setup")

    # disk
    free_gb = shutil.disk_usage(REPO).free / 1e9
    need_gb = pages * 0.0026  # ~2.6 MB/page across pages+overlay
    add(OK if free_gb > need_gb * 1.5 else WARN, "disk",
        f"{free_gb:.0f}G free, ~{need_gb:.1f}G needed for {pages}pp IR")

    # report
    print("\nPalimpsest preflight\n" + "=" * 52)
    for lvl, name, detail in rows:
        print(f"  [{lvl}] {name:16} {detail}")
    per = 14 if device == "rocm" else (10 if device == "cuda" else 32)
    mins = pages * per / 60
    print("-" * 52)
    print(f"  Extract estimate: ~{per}s/page on {device} → ~{mins:.0f} min for {pages} pp")
    bad = [r for r in rows if r[0] == BAD]
    verdict = "RED — fix BAD items (run doc-setup)" if bad else \
              ("GREEN" if all(r[0] == OK for r in rows) else "YELLOW — runnable, see WARN")
    print(f"  Verdict: {verdict}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
