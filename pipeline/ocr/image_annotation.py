#!/usr/bin/env python3
"""image_annotation — draw coloured annotation boxes from objects.csv.

**Purpose:**
Creates a visual debugging output that overlays OCR-detected objects with
colored bounding boxes and labels. Useful for verifying OCR accuracy and
inspecting which text was matched vs. unmatched against content.txt.

**Color scheme:**
- **Green:** Text matched in content.txt reference (reference_words set)
- **Red:** Text detected but not matched in content.txt (OCR extras/errors)
- **Blue:** Structural elements (lines, boxes, dividers)

**Output naming:**
Auto-detects output filename based on object types present:
- "annotated_full.png" if both text and structural objects
- "annotated_text.png" if only text objects
- "annotated_objects.png" if only structural objects
- "annotated_empty.png" if no objects

Can override with --output flag.

**Input files:**
- source/references/Page_1.png (or IMAGE_PATH env var)
- generated/ocr/{image_stem}/objects.csv (from OCR extraction)
- generated/temp/content.txt (for reference word validation)

**Output files:**
- generated/ocr/{image_stem}/annotated_*.png (annotated visualization)

**Usage:**
    python pipeline/ocr/image_annotation.py
    python pipeline/ocr/image_annotation.py --output custom_name.png
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    BLUE,
    GREEN,
    get_output_csv,
    get_image_output_dir,
    RED,
    ensure_output_dir,
    find_image,
    load_reference_words,
    normalize_text,
    read_csv_objects,
)


def _auto_output_name(text_objects: list[dict], structural_objects: list[dict]) -> str:
    """Infer the output filename from which object types are present.
    
    Args:
        text_objects: List of text/char objects
        structural_objects: List of structural objects
        
    Returns:
        str: Filename ("annotated_full.png", "annotated_text.png", etc.)
    """
    has_text = bool(text_objects)
    has_struct = bool(structural_objects)
    if has_text and has_struct:
        return "annotated_full.png"
    if has_text:
        return "annotated_text.png"
    if has_struct:
        return "annotated_objects.png"
    return "annotated_empty.png"


def annotate_image(
    image_bgr: cv2.typing.MatLike,
    text_objects: list[dict],
    structural_objects: list[dict],
    reference_words: set[str],
) -> cv2.typing.MatLike:
    """Draw bounding boxes on a copy of the image and return the annotated array.
    
    **Drawing:**
    - Text objects: Rectangle (2px) with label centered at bottom-left of box
      - GREEN if text is in reference_words (matched)
      - RED otherwise (unmatched)
    - Structural objects: BLUE rectangles with "structural" label
    
    Args:
        image_bgr: OpenCV image array (BGR, uint8)
        text_objects: List of text/char object dicts
        structural_objects: List of structural object dicts
        reference_words: Set of normalized tokens from content.txt
        
    Returns:
        cv2.typing.MatLike: Copy of input image with drawn annotations
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    out = image_bgr.copy()

    for obj in text_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        color = GREEN if normalize_text(obj["text"]) in reference_words else RED
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            out, obj["text"], (x, max(y - 3, 10)), font, 0.35, color, 1, cv2.LINE_AA
        )

    for obj in structural_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(out, (x, y), (x + w, y + h), BLUE, 2)
        cv2.putText(
            out, "structural", (x, max(y - 3, 10)), font, 0.35, BLUE, 1, cv2.LINE_AA
        )

    return out


def run(output_name: str | None = None) -> None:
    """Load image and CSV, draw annotations, save to output file.
    
    **Execution:**
    1. Find image and CSV, validate they exist
    2. Load reference tokens from content.txt
    3. Read all objects from CSV, separate text and structural
    4. Draw annotations on image copy
    5. Auto-detect output filename or use provided name
    6. Save annotated image (BGR format) to output directory
    7. Print summary statistics
    
    Args:
        output_name: Optional custom output filename. If None, auto-detects.
    """
    image_path = find_image()
    output_csv = get_output_csv(image_path)
    output_dir = get_image_output_dir(image_path)

    ensure_output_dir(image_path)

    if not output_csv.exists():
        sys.exit(
            f"ERROR: '{output_csv}' not found.\n"
            "Run prepare_pipeline.py (and at least one extraction script) first."
        )

    all_objects = read_csv_objects(output_csv)
    text_objects = [o for o in all_objects if o["object_type"] in ("text", "char")]
    structural_objects = [o for o in all_objects if o["object_type"] == "structural"]

    if not all_objects:
        print("[image_annotation] WARNING: CSV is empty – nothing to annotate.")

    reference_words = load_reference_words()

    image_bgr = cv2.imread(str(find_image()))
    if image_bgr is None:
        raise RuntimeError("OpenCV could not load the input image.")

    print("[image_annotation] Drawing annotations …")
    annotated = annotate_image(
        image_bgr, text_objects, structural_objects, reference_words
    )

    if output_name is None:
        output_name = _auto_output_name(text_objects, structural_objects)

    out_path = output_dir / output_name
    cv2.imwrite(str(out_path), annotated)

    matched = sum(
        1 for o in text_objects if normalize_text(o["text"]) in reference_words
    )
    unmatched = len(text_objects) - matched

    print(f"[image_annotation] Saved → {output_name}")
    print(
        f"  Text objects : {len(text_objects):4d}  ({matched} green / {unmatched} red)"
    )
    print(f"  Structural   : {len(structural_objects):4d}  (blue)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Annotate a resume image from the objects CSV."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output filename (default: auto-detected from CSV contents)",
    )
    args = parser.parse_args()
    run(output_name=args.output)
