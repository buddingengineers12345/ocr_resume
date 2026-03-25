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
    """Validate input files and initialize OCR output directory structure.
    
    Checks that input image and content.txt exist, creates output directory
    (generated/ocr/{image_stem}/), and initializes an empty objects.csv file.
    
    **Steps:**
    1. Find input image via find_image()
    2. Verify content.txt exists in generated/temp/
    3. Create output directory with mkdir(parents=True)
    4. Write objects.csv with header row (no data yet)
    5. Print summary
    
    **Raises:**
        FileNotFoundError: If input image or content.txt not found
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
