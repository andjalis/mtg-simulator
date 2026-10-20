"""Measure round 16 separately, preserving the 2026-10-20 baseline artifacts.

Run from the repo root: python3 -m results.standard_coverage.round16
"""
from .remeasure import main


if __name__ == "__main__":
    main("round16")
