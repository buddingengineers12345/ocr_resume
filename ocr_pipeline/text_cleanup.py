#!/usr/bin/env python3
"""
text_cleanup.py
===============
Standalone utility (not part of the numbered pipeline steps).

Reads bounding boxes from objects.csv (text rows only), determines the
background colour of each region, and fills every bounding box with that
colour so the text becomes invisible.

Improvements:
- Better background color estimation using bilateral filtering
- Morphological cleanup for smoother results
- Overlay functionality to blend original and cleaned images
- Generates output/text_cleaned.png and output/text_cleaned_overlay.png

Usage:
  python ocr_pipeline/text_cleanup.py          # from workspace root
  python text_cleanup.py                        # from inside ocr_pipeline/
"""

import sys
from pathlib import Path

# Allow running from either the workspace root or from inside ocr_pipeline/
sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np

from utils import SCRIPT_DIR, OUTPUT_CSV, OUTPUT_DIR, find_image, read_csv_objects

# ── Background colour estimation ──────────────────────────────────────────────

def estimate_background_color(image_bgr: np.ndarray, x: int, y: int,
                               w: int, h: int, margin: int = 8,
                               sample_size: int = 50) -> tuple:
    """
    Estimate the background colour of a bounding-box region using an improved algorithm.

    Strategy:
    1. Sample a larger border ring (expanded by `margin` pixels)
    2. Apply bilateral filtering to smooth and denoise the sample
    3. Find the most frequent colour in the filtered border
    4. Falls back to white if the border is insufficient

    This handles varying backgrounds and noise better than the original approach.

    Returns a BGR tuple of ints.
    """
    img_h, img_w = image_bgr.shape[:2]

    # Outer rectangle (expanded by margin)
    ox1 = max(x - margin, 0)
    oy1 = max(y - margin, 0)
    ox2 = min(x + w + margin, img_w)
    oy2 = min(y + h + margin, img_h)

    outer = image_bgr[oy1:oy2, ox1:ox2].copy()

    if outer.size == 0:
        return (255, 255, 255)

    # Apply bilateral filtering to denoise and smooth the border region
    # This helps with inconsistent backgrounds
    if outer.shape[0] > 2 and outer.shape[1] > 2:
        outer = cv2.bilateralFilter(outer, 9, 75, 75)

    # Inner rectangle mask – True for pixels that belong to the box itself
    inner_x1 = max(x - ox1, 0)
    inner_y1 = max(y - oy1, 0)
    inner_x2 = min(inner_x1 + w, outer.shape[1])
    inner_y2 = min(inner_y1 + h, outer.shape[0])

    mask = np.zeros(outer.shape[:2], dtype=bool)
    if inner_x2 > inner_x1 and inner_y2 > inner_y1:
        mask[inner_y1:inner_y2, inner_x1:inner_x2] = True

    border_pixels = outer[~mask]  # pixels in the outer ring only

    if border_pixels.size == 0:
        return (255, 255, 255)

    # Reshape and find the most common BGR colour
    border_pixels = border_pixels.reshape(-1, 3)

    # Use k-means to find the dominant color cluster (more robust than mode)
    if len(border_pixels) > 0:
        # Simple approach: find the median color in the border
        median_color = np.median(border_pixels, axis=0).astype(int)
        return tuple(median_color.tolist())

    return (255, 255, 255)


# ── Overlay generation ────────────────────────────────────────────────────────

def create_overlay(original_path: Path, cleaned_path: Path, 
                   alpha: float = 0.6) -> np.ndarray:
    """
    Create an overlay image that blends the original and cleaned versions.
    
    Args:
        original_path: Path to the original image (page_1.png)
        cleaned_path: Path to the cleaned image (text_cleaned.png)
        alpha: Transparency factor (0.0-1.0) for the original image over cleaned
               0.0 = show only cleaned, 1.0 = show only original
    
    Returns:
        The blended image as a numpy array
    """
    original = cv2.imread(str(original_path))
    cleaned = cv2.imread(str(cleaned_path))
    
    if original is None or cleaned is None:
        print("ERROR: Could not read one or both images for overlay.")
        return None
    
    # Ensure both images have the same dimensions
    if original.shape != cleaned.shape:
        cleaned = cv2.resize(cleaned, (original.shape[1], original.shape[0]))
    
    # Blend using weighted addition
    # overlay = alpha * original + (1 - alpha) * cleaned
    overlay = cv2.addWeighted(original, alpha, cleaned, 1 - alpha, 0)
    
    return overlay

def main():
    # ── Locate inputs ──────────────────────────────────────────────────────────
    image_path = find_image()
    csv_path   = SCRIPT_DIR / OUTPUT_CSV

    if not csv_path.exists():
        print(f"ERROR: objects.csv not found at {csv_path}")
        sys.exit(1)

    print(f"Image : {image_path}")
    print(f"CSV   : {csv_path}")

    # ── Load image ─────────────────────────────────────────────────────────────
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"ERROR: Could not read image '{image_path}'.")
        sys.exit(1)

    img_h, img_w = image.shape[:2]
    cleaned = image.copy()  # Create working copy for cleanup

    # ── Load bounding boxes ────────────────────────────────────────────────────
    all_objects = read_csv_objects(csv_path)
    text_boxes  = [obj for obj in all_objects if obj["object_type"] == "text"]

    if not text_boxes:
        print("No text rows found in objects.csv – nothing to clean.")
        sys.exit(0)

    print(f"Processing {len(text_boxes)} text region(s)...")

    # ── Fill each bounding box with its background colour ─────────────────────
    for obj in text_boxes:
        x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]

        # Clamp coordinates to image bounds
        x1 = max(x, 0)
        y1 = max(y, 0)
        x2 = min(x + w, img_w)
        y2 = min(y + h, img_h)

        if x2 <= x1 or y2 <= y1:
            continue  # degenerate box

        bg_color = estimate_background_color(image, x, y, w, h)
        cv2.rectangle(cleaned, (x1, y1), (x2, y2), bg_color, thickness=-1)

    # ── Apply morphological cleanup for smoother results ──────────────────────
    print("Smoothing filled regions...")
    
    # Small morphological operations to smooth the filled areas
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Optional: light bilateral filtering for smoother transitions
    cleaned = cv2.bilateralFilter(cleaned, 5, 50, 50)

    # ── Save cleaned image ────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_path = OUTPUT_DIR / "text_cleaned.png"
    cv2.imwrite(str(cleaned_path), cleaned)
    print(f"Saved : {cleaned_path}")

    # ── Create and save overlay image ─────────────────────────────────────────
    print("Creating overlay image...")
    overlay = create_overlay(image_path, cleaned_path, alpha=0.5)
    
    if overlay is not None:
        overlay_path = OUTPUT_DIR / "text_cleaned_overlay.png"
        cv2.imwrite(str(overlay_path), overlay)
        print(f"Saved : {overlay_path}")
    else:
        print("WARNING: Failed to create overlay image.")


if __name__ == "__main__":
    main()
