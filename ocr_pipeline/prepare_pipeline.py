#!/usr/bin/env python3
"""
prepare_pipeline.py
===================
Step 1 of the OCR pipeline.

- Validates that the input image and content.txt exist.
- Initialises a fresh objects.csv (headers only), clearing any previous run.

Usage:
  python ocr_pipeline/prepare_pipeline.py   # from workspace root
  python prepare_pipeline.py                # from inside ocr_pipeline/
"""

import csv
import sys
from pathlib import Path

# Ensure sibling utils.py is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

from utils import SCRIPT_DIR, TEMP_DIR, OUTPUT_CSV, CSV_FIELDNAMES, find_image, get_content_path


def prepare():
    image_path   = find_image()
    content_path = get_content_path()
    csv_path     = SCRIPT_DIR / OUTPUT_CSV

    print(f"[prepare] Image   : {image_path.name}")
    print(f"[prepare] Content : {content_path.name}")

    # Create a fresh CSV with headers only
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

    print(f"[prepare] CSV initialised → {csv_path.name}")


if __name__ == "__main__":
    prepare()
