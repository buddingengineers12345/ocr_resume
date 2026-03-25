#!/usr/bin/env python3
"""
text_cleanup.py
===============
Step 3a of the OCR pipeline (runs between text_extraction and object_extraction).

Reads bounding boxes from objects.csv (text rows only), estimates the background
colour of each region, and fills every bounding box with that colour so the text
becomes invisible before structural-object detection.

Generates:
  output/text_cleaned.png

Usage:
  python ocr_pipeline/text_cleanup.py   # from workspace root
  python text_cleanup.py                # from inside ocr_pipeline/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np
from utils import get_output_csv, get_image_output_dir, find_image, read_csv_objects

# ── Background colour estimation ──────────────────────────────────────────────

_INNER_MARGIN = 1  # px from bounding-box edge for inner border sampling
_MIN_INNER_PIXELS = 10  # minimum inner-border pixels to trust the sample


def estimate_background_color(
    image_bgr: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    margin: int = 8,
) -> tuple[int, int, int]:
    """Estimate the background colour inside a bounding box.

    Strategy:
    1. Sample the inner border (1 px from the box edge) — closest to where
       background colour is likely intact.
    2. If insufficient samples, fall back to the outer margin with IQR
       outlier filtering and bilateral denoising.

    Returns a BGR tuple of ints.
    """
    img_h, img_w = image_bgr.shape[:2]

    inner_x1 = max(x + _INNER_MARGIN, 0)
    inner_y1 = max(y + _INNER_MARGIN, 0)
    inner_x2 = min(x + w - _INNER_MARGIN, img_w)
    inner_y2 = min(y + h - _INNER_MARGIN, img_h)

    inner_border_pixels = None
    if inner_x2 > inner_x1 and inner_y2 > inner_y1:
        inner_region = image_bgr[inner_y1:inner_y2, inner_x1:inner_x2]
        border_mask = np.zeros(inner_region.shape[:2], dtype=bool)
        border_mask[0, :] = True
        border_mask[-1, :] = True
        border_mask[:, 0] = True
        border_mask[:, -1] = True
        inner_border = inner_region[border_mask]
        if len(inner_border) > _MIN_INNER_PIXELS // 2:
            inner_border_pixels = inner_border

    if inner_border_pixels is not None and len(inner_border_pixels) > _MIN_INNER_PIXELS:
        inner_encoded = (
            inner_border_pixels[:, 0].astype(np.uint32)
            | (inner_border_pixels[:, 1].astype(np.uint32) << 8)
            | (inner_border_pixels[:, 2].astype(np.uint32) << 16)
        )
        unique, counts = np.unique(inner_encoded, return_counts=True)
        dominant = unique[np.argmax(counts)]
        return (
            int(dominant & 0xFF),
            int((dominant >> 8) & 0xFF),
            int((dominant >> 16) & 0xFF),
        )

    # Fall back to outer margin with outlier filtering
    ox1 = max(x - margin, 0)
    oy1 = max(y - margin, 0)
    ox2 = min(x + w + margin, img_w)
    oy2 = min(y + h + margin, img_h)

    outer = image_bgr[oy1:oy2, ox1:ox2].copy()
    if outer.size == 0:
        return (255, 255, 255)

    if outer.shape[0] > 2 and outer.shape[1] > 2:  # noqa: PLR2004
        outer = cv2.bilateralFilter(outer, 9, 75, 75)

    # Create mask for border pixels (outside the text box)
    inner_x1_rel = max(x - ox1, 0)
    inner_y1_rel = max(y - oy1, 0)
    inner_x2_rel = min(inner_x1_rel + w, outer.shape[1])
    inner_y2_rel = min(inner_y1_rel + h, outer.shape[0])

    mask = np.zeros(outer.shape[:2], dtype=bool)
    if inner_x2_rel > inner_x1_rel and inner_y2_rel > inner_y1_rel:
        mask[inner_y1_rel:inner_y2_rel, inner_x1_rel:inner_x2_rel] = True

    border_pixels = outer[~mask].reshape(-1, 3)

    if border_pixels.size == 0:
        return (255, 255, 255)

    # Filter outliers using IQR before selecting the dominant colour
    brightness = np.mean(border_pixels, axis=1)
    q1 = np.percentile(brightness, 25)
    q3 = np.percentile(brightness, 75)
    iqr = q3 - q1
    valid_mask = (brightness >= q1 - 1.5 * iqr) & (brightness <= q3 + 1.5 * iqr)
    filtered_pixels = border_pixels[valid_mask]

    if len(filtered_pixels) == 0:
        return tuple(np.median(border_pixels, axis=0).astype(int).tolist())

    filtered_encoded = (
        filtered_pixels[:, 0].astype(np.uint32)
        | (filtered_pixels[:, 1].astype(np.uint32) << 8)
        | (filtered_pixels[:, 2].astype(np.uint32) << 16)
    )

    unique, counts = np.unique(filtered_encoded, return_counts=True)
    dominant = unique[np.argmax(counts)]
    return (
        int(dominant & 0xFF),
        int((dominant >> 8) & 0xFF),
        int((dominant >> 16) & 0xFF),
    )


def main() -> None:
    image_path = find_image()
    output_csv = get_output_csv(image_path)
    output_dir = get_image_output_dir(image_path)

    if not output_csv.exists():
        print(f"ERROR: objects.csv not found at {output_csv}")
        sys.exit(1)

    print(f"Image : {image_path}")
    print(f"CSV   : {output_csv}")

    image = cv2.imread(str(image_path))
    if image is None:
        print(f"ERROR: Could not read image '{image_path}'.")
        sys.exit(1)

    img_h, img_w = image.shape[:2]
    cleaned = image.copy()

    all_objects = read_csv_objects(output_csv)
    text_boxes = [obj for obj in all_objects if obj["object_type"] in ("text", "char")]

    if not text_boxes:
        print("No text rows found in objects.csv – nothing to clean.")
        sys.exit(0)

    print(f"Processing {len(text_boxes)} text region(s)…")

    for obj in text_boxes:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
        x1, y1 = max(x, 0), max(y, 0)
        x2, y2 = min(x + w, img_w), min(y + h, img_h)
        if x2 <= x1 or y2 <= y1:
            continue
        bg_color = estimate_background_color(image, x, y, w, h)
        cv2.rectangle(cleaned, (x1, y1), (x2, y2), bg_color, thickness=-1)

    print("Smoothing filled regions…")
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    cleaned = cv2.bilateralFilter(cleaned, 5, 50, 50)

    output_dir.mkdir(parents=True, exist_ok=True)
    cleaned_path = output_dir / "text_cleaned.png"
    cv2.imwrite(str(cleaned_path), cleaned)
    print(f"Saved : {cleaned_path}")


if __name__ == "__main__":
    main()
