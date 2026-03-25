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

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    CSV_FIELDNAMES,
    get_output_csv,
    ensure_output_dir,
    find_image,
    get_content_path,
)


def prepare() -> None:
    image_path = find_image()
    content_path = get_content_path()
    ensure_output_dir(image_path)

    print(f"[prepare] Image   : {image_path.name}")
    print(f"[prepare] Content : {content_path.name}")

    output_csv = get_output_csv(image_path)
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()

    print(f"[prepare] CSV initialised → {output_csv.name}")


if __name__ == "__main__":
    prepare()
