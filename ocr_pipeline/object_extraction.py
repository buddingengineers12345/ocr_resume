#!/usr/bin/env python3
"""
object_extraction.py
====================
Step 3 of the OCR pipeline.

Detects structural elements (lines, dividers, boxes) using OpenCV morphological
operations, then writes the structural objects into objects.csv (replacing any
previous structural rows while preserving text rows from prior runs).

When run standalone (without a prior text_extraction step), any existing text
rows in objects.csv are used for overlap filtering so that structural detections
do not clobber text regions.

Usage:
  python ocr_pipeline/object_extraction.py   # from workspace root
  python object_extraction.py                # from inside ocr_pipeline/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    SCRIPT_DIR, OUTPUT_DIR, OUTPUT_CSV,
    find_image, read_csv_objects, update_csv_objects, overlaps_text,
)


def detect_structural(image_bgr, text_boxes: list) -> list:
    """
    Detect structural elements via morphological line extraction + contour analysis.

    Strategy:
      1. Binarise (inverted so ink = white).
      2. Isolate horizontal lines with a wide, 1-pixel-tall kernel.
      3. Isolate vertical lines with a tall, 1-pixel-wide kernel.
      4. Combine and dilate to merge close fragments.
      5. Find contours; discard those dominated by text regions.

    Returns a list of dicts: {object_type, text, x, y, w, h}.
    """
    import cv2

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Otsu binarisation – inverted (structural marks become white)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    img_h, img_w = binary.shape

    # Horizontal lines
    h_len    = max(40, img_w // 20)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    h_lines  = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=2)

    # Vertical lines
    v_len    = max(40, img_h // 20)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    v_lines  = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=2)

    # Closed rectangular shapes (boxes) – combine H + V then dilate to close gaps
    box_mask    = cv2.add(h_lines, v_lines)
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    box_mask    = cv2.dilate(box_mask, rect_kernel, iterations=2)

    # Merge all structural masks
    combined   = cv2.add(h_lines, cv2.add(v_lines, box_mask))
    dil_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    combined   = cv2.dilate(combined, dil_kernel, iterations=1)

    contours, _ = cv2.findContours(
        combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    MIN_SPAN = 20  # discard tiny noise contours

    objects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if max(w, h) < MIN_SPAN:
            continue
        if overlaps_text(x, y, w, h, text_boxes):
            continue
        objects.append({
            "object_type": "structural",
            "text": "",
            "x": x, "y": y, "w": w, "h": h,
        })

    return objects


def run():
    import cv2

    # Check if cleaned text image exists; otherwise use the original image
    cleaned_image_path = OUTPUT_DIR / "text_cleaned.png"
    if cleaned_image_path.exists():
        image_path = cleaned_image_path
        print("[object_extraction] Using text_cleaned.png (text regions removed)")
    else:
        image_path = find_image()
        print("[object_extraction] Using original image (text_cleaned.png not found)")

    csv_path   = SCRIPT_DIR / OUTPUT_CSV

    # Use existing text rows (if any) for overlap filtering
    existing   = read_csv_objects(csv_path) if csv_path.exists() else []
    text_boxes = [o for o in existing if o["object_type"] == "text"]

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise RuntimeError(f"OpenCV could not load '{image_path}'.")

    print("[object_extraction] Detecting structural objects …")
    structural_objects = detect_structural(image_bgr, text_boxes)
    print(f"[object_extraction] {len(structural_objects)} structural objects detected.")

    update_csv_objects(structural_objects, "structural", csv_path)
    print(f"[object_extraction] CSV updated → {csv_path.name}")


if __name__ == "__main__":
    run()
