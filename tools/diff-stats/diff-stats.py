#!/usr/bin/env python3
"""Run the src-layout diff_stats package without installing it."""

import runpy
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    runpy.run_module("diff_stats", run_name="__main__")


if __name__ == "__main__":
    main()
