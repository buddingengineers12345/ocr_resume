#!/usr/bin/env python3
"""
image_annotation.py
===================
Final step of the OCR pipeline.

Reads objects from objects.csv and draws coloured bounding boxes on the source image:
  - Green  : text word found in content.txt
  - Red    : text word NOT found in content.txt
  - Blue   : structural element

The output filename is chosen automatically based on the object types present
in the CSV, or can be overridden with --output:
  annotated_text.png    – text objects only
  annotated_objects.png – structural objects only
  annotated_full.png    – both text and structural objects

Usage:
  python ocr_pipeline/image_annotation.py [--output FILENAME]
  python image_annotation.py [--output FILENAME]   # from inside ocr_pipeline/
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SCRIPT_DIR, OUTPUT_DIR, OUTPUT_CSV,
    GREEN, RED, BLUE,
    find_image, load_reference_words, normalize_text, read_csv_objects,
    ensure_output_dir,
)


def _auto_output_name(text_objects: list, structural_objects: list) -> str:
    """Infer the output filename from which object types are present."""
    has_text   = bool(text_objects)
    has_struct = bool(structural_objects)
    if has_text and has_struct:
        return "annotated_full.png"
    if has_text:
        return "annotated_text.png"
    if has_struct:
        return "annotated_objects.png"
    return "annotated_empty.png"


def annotate_image(image_bgr, text_objects: list,
                   structural_objects: list, reference_words: set):
    """
    Draw bounding boxes on a copy of the image and return the annotated array.
    """
    import cv2

    THICKNESS  = 2
    FONT       = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.35
    FONT_THICK = 1

    out = image_bgr.copy()

    for obj in text_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        color = GREEN if normalize_text(obj["text"]) in reference_words else RED
        cv2.rectangle(out, (x, y), (x + w, y + h), color, THICKNESS)
        cv2.putText(
            out, obj["text"], (x, max(y - 3, 10)),
            FONT, FONT_SCALE, color, FONT_THICK, cv2.LINE_AA,
        )

    for obj in structural_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(out, (x, y), (x + w, y + h), BLUE, THICKNESS)
        cv2.putText(
            out, "structural", (x, max(y - 3, 10)),
            FONT, FONT_SCALE, BLUE, FONT_THICK, cv2.LINE_AA,
        )

    return out


def run(output_name: str = None):
    import cv2

    ensure_output_dir()

    image_path = find_image()
    csv_path   = SCRIPT_DIR / OUTPUT_CSV

    if not csv_path.exists():
        sys.exit(
            f"ERROR: '{OUTPUT_CSV}' not found.\n"
            "Run prepare_pipeline.py (and at least one extraction script) first."
        )

    all_objects        = read_csv_objects(csv_path)
    text_objects       = [o for o in all_objects if o["object_type"] == "text"]
    structural_objects = [o for o in all_objects if o["object_type"] == "structural"]

    if not all_objects:
        print("[image_annotation] WARNING: CSV is empty – nothing to annotate.")

    reference_words = load_reference_words()

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise RuntimeError(f"OpenCV could not load '{image_path}'.")

    print("[image_annotation] Drawing annotations …")
    annotated = annotate_image(image_bgr, text_objects, structural_objects, reference_words)

    if output_name is None:
        output_name = _auto_output_name(text_objects, structural_objects)

    out_path = OUTPUT_DIR / output_name
    cv2.imwrite(str(out_path), annotated)

    matched   = sum(1 for o in text_objects if normalize_text(o["text"]) in reference_words)
    unmatched = len(text_objects) - matched

    print(f"[image_annotation] Saved → {output_name}")
    print(f"  Text objects : {len(text_objects):4d}  ({matched} green / {unmatched} red)")
    print(f"  Structural   : {len(structural_objects):4d}  (blue)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Annotate a resume image from the objects CSV."
    )
    parser.add_argument(
        "--output", default=None,
        help="Output filename (default: auto-detected from CSV contents)"
    )
    args = parser.parse_args()
    run(output_name=args.output)
