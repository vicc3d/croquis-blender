#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy the drawing core in from IngeTrazo Croquis, where it lives.

    python3 tools/sync_core.py [path/to/ingetrazo-croquis]

One drawing core serves IngeTrazo and Blender: it is written and tested in
github.com/vicc3d/ingetrazo-croquis (``croquis/``), and copied here, into
``croquis_blender/core/``, when it improves. The copy says which commit it
came from.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "croquis_blender" / "core"
#: The drawing, without IngeTrazo's panel, live preview or Qt export.
MODULES = ("compose", "drawing", "hatch", "ink", "marker", "palette", "paper",
           "presets", "raster", "shadow", "strokes", "texts", "vector",
           "visibility", "watercolour")


def main() -> int:
    src_repo = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "ingetrazo-croquis"
    src = src_repo / "croquis"
    if not (src / "drawing.py").is_file():
        print(f"no IngeTrazo Croquis checkout at {src_repo}")
        return 2
    try:
        commit = subprocess.check_output(["git", "-C", str(src_repo), "rev-parse", "--short",
                                          "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    CORE.mkdir(parents=True, exist_ok=True)
    for name in MODULES:
        shutil.copy2(src / f"{name}.py", CORE / f"{name}.py")
    (CORE / "__init__.py").write_text(
        '"""IngeTrazo Croquis\'s drawing core (github.com/vicc3d/ingetrazo-croquis,\n'
        f'commit {commit}), copied in by tools/sync_core.py: change it there."""\n',
        encoding="utf-8")
    print(f"core synced from {src_repo} @ {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
