#!/usr/bin/env python3
"""object_extraction — detect structural page elements using OpenCV.

Finds contours representing lines, boxes and dividers via morphology and
edge detection, filters those that overlap text regions and writes structural
rows into the objects CSV. Can operate with or without a prior text-extraction
pass; existing text rows are respected to avoid overwriting.

Usage:
        python pipeline/ocr/object_extraction.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    BLUE,
    get_output_csv,
    get_image_output_dir,
    ensure_output_dir,
    estimate_colors,
    find_image,
    overlaps_text,
    read_csv_objects,
    update_csv_objects,
)


def detect_structural(image_bgr, text_boxes: list, image_original=None) -> list:
    """
    Detect structural elements via adaptive thresholding and edge detection.

    Strategy:
      1. Convert to grayscale.
      2. Apply adaptive threshold (better separation for varying lighting).
      3. Light morphology to remove noise without merging objects.
      4. Apply Canny edge detection to preserve boundaries.
      5. Combine region and edge info.
      6. Find contours; discard those dominated by text regions.

    *image_original* is used for colour estimation when provided (e.g. when
    *image_bgr* is the text-cleaned variant).  Falls back to *image_bgr*.

    Returns a list of dicts: {object_type, text, x, y, w, h, color, bg_color}.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold (better separation than fixed Otsu)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )

    # Light morphology (remove noise, don't merge objects)
    kernel = np.ones((2, 2), np.uint8)
    clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Edge detection (preserve boundaries)
    edges = cv2.Canny(gray, 50, 150)

    # Combine region + edge info
    combined = cv2.bitwise_or(clean, edges)

    # Find contours
    contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

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

        color_img = image_original if image_original is not None else image_bgr
        color, bg_color = estimate_colors(color_img, x, y, w, h)

        objects.append(
            {
                "object_type": "structural",
                "text": "",
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "color": color,
                "bg_color": bg_color,
            }
        )

    return objects


def run():
    import cv2

    image_source = find_image()
    output_dir = get_image_output_dir(image_source)
    output_csv = get_output_csv(image_source)

    # Check if cleaned text image exists; otherwise use the original image
    cleaned_image_path = output_dir / "text_cleaned.png"
    if cleaned_image_path.exists():
        image_path = cleaned_image_path
        print("[object_extraction] Using text_cleaned.png (text regions removed)")
    else:
        image_path = image_source
        print("[object_extraction] Using original image (text_cleaned.png not found)")

    ensure_output_dir(image_source)

    # Use existing text rows (if any) for overlap filtering
    existing = read_csv_objects(output_csv) if output_csv.exists() else []
    text_boxes = [o for o in existing if o["object_type"] in ("text", "char")]

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is None:
        raise RuntimeError(f"OpenCV could not load '{image_path}'.")

    # Load original image for colour sampling when using text_cleaned.png
    image_original = None
    if image_path != image_source:
        image_original = cv2.imread(str(image_source))

    print("[object_extraction] Detecting structural objects …")
    structural_objects = detect_structural(image_bgr, text_boxes, image_original)
    print(f"[object_extraction] {len(structural_objects)} structural objects detected.")

    update_csv_objects(structural_objects, "structural", output_csv)
    print(f"[object_extraction] CSV updated → {output_csv.name}")

    # Visualize and save detected structural objects
    vis = image_bgr.copy()
    THICKNESS = 2
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.35
    FONT_THICK = 1

    for obj in structural_objects:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), BLUE, THICKNESS)
        cv2.putText(
            vis,
            "structural",
            (x, max(y - 3, 10)),
            FONT,
            FONT_SCALE,
            BLUE,
            FONT_THICK,
            cv2.LINE_AA,
        )

    out_path = output_dir / "object_detected.png"
    cv2.imwrite(str(out_path), vis)
    print(f"[object_extraction] Saved visualization → {out_path.name}")


if __name__ == "__main__":
    run()
