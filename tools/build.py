#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the extension's zip with Blender's own ``extension build``:

    python3 tools/build.py [--blender /path/to/blender]

Leaves build/croquis-blender-<version>.zip.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", default="blender")
    args = ap.parse_args()
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    rc = subprocess.call([args.blender, "--command", "extension", "build",
                          "--source-dir", str(ROOT / "croquis_blender"),
                          "--output-dir", str(out)])
    if rc == 0:
        for z in out.glob("croquis-*.zip"):
            if not z.name.startswith("croquis-blender-"):
                z.replace(out / z.name.replace("croquis-", "croquis-blender-", 1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
