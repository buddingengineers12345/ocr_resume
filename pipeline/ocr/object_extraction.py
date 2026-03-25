#!/usr/bin/env python3
"""object_extraction — detect structural page elements using OpenCV.

**Purpose:**
Finds lines, boxes, dividers and other non-text structural elements using
morphological operations and edge detection. Filters results by text region
overlaps and writes them to objects.csv. Works with or without prior text
extraction (respects existing text rows).

**Detection strategy:**
1. Convert image to grayscale
2. Apply adaptive threshold for lighting invariance
3. Light morphology to remove noise without merging objects
4. Canny edge detection to preserve object boundaries
5. Combine thresholded regions and edges
6. Find contours and extract bounding boxes
7. Filter overlaps with detected text regions
8. Estimate foreground/background colors
9. Write structural objects to CSV

**Noise filtering:**
- Removes contours with area < 20 pixels
- Skips objects that cover > 90% of the image (page edges/sidebars)
- Skips objects overlapping text regions (>50% coverage threshold)

**Key feature:** Can optionally use text_cleaned.png (with text regions pre-filled)
for cleaner structural detection. Falls back to original image if unavailable.

**Input files:**
- source/references/Page_1.png (original image)
- generated/ocr/{image_stem}/text_cleaned.png (optional, preferred)
- generated/ocr/{image_stem}/objects.csv (for existing text rows)

**Output files:**
- generated/ocr/{image_stem}/objects.csv (structural objects appended)

**Usage:**
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
    """Detect structural elements via adaptive thresholding and edge detection.

    **Two-image mode:**
    - image_bgr: Detection/processing image (can be text_cleaned.png with text erased)
    - image_original: Color sampling image (original, for accurate colors)
    
    This allows clean structural detection on text-removed image while maintaining
    accurate color estimates from the original.

    **Processing pipeline:**
    1. Convert to grayscale
    2. Apply adaptive Gaussian threshold (robust to lighting variations)
    3. Light morphology (remove noise without merging structures)
    4. Canny edge detection (preserve structure boundaries)
    5. Combine thresholded regions and edges
    6. Find contours and extract bounding rectangles
    7. Filter by size (< 20px), coverage (> 90%), and text overlap (> 50%)
    8. Estimate colors from regions
    
    Args:
        image_bgr: OpenCV BGR image for detection (can be text-cleaned)
        text_boxes: List of existing text boxes to filter overlaps
        image_original: Optional original image for color estimation (BGR)
        
    Returns:
        list[dict]: Structural objects with keys: object_type, text (empty),
        x, y, w, h, color, bg_color
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
    """Load image, detect structural elements, append to objects CSV.
    
    **Workflow:**
    1. Find source image and output directory
    2. Check if text_cleaned.png exists (better structural detection)
    3. Use cleaned or original image accordingly
    4. Load existing text boxes from CSV for overlap filtering
    5. Detect structural elements using detect_structural()
    6. Update CSV with structural object rows
    7. Create annotated visualization (annotated_objects.png)
    8. Print summary statistics
    """
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
