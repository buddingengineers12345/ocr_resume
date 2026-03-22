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
    BLUE, ensure_output_dir,
)


def detect_structural(image_bgr, text_boxes: list) -> list:
    """
    Detect structural elements via adaptive thresholding and edge detection.

    Strategy:
      1. Convert to grayscale.
      2. Apply adaptive threshold (better separation for varying lighting).
      3. Light morphology to remove noise without merging objects.
      4. Apply Canny edge detection to preserve boundaries.
      5. Combine region and edge info.
      6. Find contours; discard those dominated by text regions.

    Returns a list of dicts: {object_type, text, x, y, w, h}.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold (better separation than fixed Otsu)
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11, 2
    )

    # Light morphology (remove noise, don't merge objects)
    kernel = np.ones((2, 2), np.uint8)
    clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Edge detection (preserve boundaries)
    edges = cv2.Canny(gray, 50, 150)

    # Combine region + edge info
    combined = cv2.bitwise_or(clean, edges)

    # Find contours
    contours, _ = cv2.findContours(
        combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    MIN_SPAN = 20  # discard tiny noise contours

    objects = []
    for cnt in contours:
        area = cv2.contourArea(cnt)

        # Filter very small noise
        if area < 20:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        # Optional: filter very large region (sidebar/page edge)
        if w > 0.9 * image_bgr.shape[1] and h > 0.9 * image_bgr.shape[0]:
            continue

        if overlaps_text(x, y, w, h, text_boxes, threshold=0.5):
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
    text_boxes = [o for o in existing if o["object_type"] in ("text", "char")]

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise RuntimeError(f"OpenCV could not load '{image_path}'.")

    print("[object_extraction] Detecting structural objects …")
    structural_objects = detect_structural(image_bgr, text_boxes)
    print(f"[object_extraction] {len(structural_objects)} structural objects detected.")

    update_csv_objects(structural_objects, "structural", csv_path)
    print(f"[object_extraction] CSV updated → {csv_path.name}")
    
    # Visualize and save detected structural objects
    ensure_output_dir()
    vis = image_bgr.copy()
    THICKNESS = 2
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.35
    FONT_THICK = 1
    
    for obj in structural_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), BLUE, THICKNESS)
        cv2.putText(
            vis, "structural", (x, max(y - 3, 10)),
            FONT, FONT_SCALE, BLUE, FONT_THICK, cv2.LINE_AA,
        )
    
    out_path = OUTPUT_DIR / "object_detected.png"
    cv2.imwrite(str(out_path), vis)
    print(f"[object_extraction] Saved visualization → {out_path.name}")


if __name__ == "__main__":
    run()
