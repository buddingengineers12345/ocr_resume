#!/usr/bin/env python3
"""prepare_pipeline — initialize OCR run output and validate inputs.

**Purpose:**
Validates that all prerequisites for OCR processing exist, then initializes
empty output CSV files and directories. This is the preparation step before
any OCR text extraction or structural object detection runs.

**Validation checks:**
1. Input image exists in source/references/ (or via IMAGE_PATH env var)
2. content.txt exists in generated/temp/ (from extract_values.py)

**Initialization:**
1. Creates per-image output directory: generated/ocr/{image_stem}/
2. Initializes objects.csv with header row only (ready for data rows)

**Input files:**
- source/references/Page_1.png or IMAGE_PATH environment variable
- generated/temp/content.txt (from extract_values.py)

**Output files:**
- generated/ocr/{image_stem}/objects.csv (empty, headers only)

**Usage:**
    python pipeline/ocr/prepare_pipeline.py
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
    """Validate prerequisites and initialize OCR output directories and CSV.
    
    **Execution flow:**
    1. Find input image (via find_image() — checks IMAGE_PATH env var, then defaults)
    2. Find content.txt in temp/ (validates it exists from extract_values.py)
    3. Ensure output directory exists: generated/ocr/{image_stem}/
    4. Write empty objects.csv with CSV_FIELDNAMES header row
    5. Print initialization summary
    
    **Raises:**
    - FileNotFoundError if image or content.txt not found
    """
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
