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
                               w: int, h: int, margin: int = 8) -> tuple:
    """
    Estimate the background colour of a bounding-box region using an advanced algorithm.

    Strategy:
    1. Sample from INNER margin first (closest to text, most likely background)
    2. If insufficient, expand to outer margin
    3. Filter outliers using IQR (Interquartile Range) method
    4. Use mode (most common color) for robustness

    This handles text on light backgrounds surrounded by dark areas.

    Returns a BGR tuple of ints.
    """
    img_h, img_w = image_bgr.shape[:2]

    # Priority 1: Sample from INNER margin (2-4px from edge)
    inner_margin_min = 1
    inner_margin_max = 3
    
    inner_x1 = max(x + inner_margin_min, 0)
    inner_y1 = max(y + inner_margin_min, 0)
    inner_x2 = min(x + w - inner_margin_min, img_w)
    inner_y2 = min(y + h - inner_margin_min, img_h)

    inner_border_pixels = None
    if inner_x2 > inner_x1 and inner_y2 > inner_y1:
        inner_region = image_bgr[inner_y1:inner_y2, inner_x1:inner_x2]
        
        # Create border mask (pixels at edges of inner region)
        border_mask = np.zeros(inner_region.shape[:2], dtype=bool)
        border_mask[0, :] = True  # Top
        border_mask[-1, :] = True  # Bottom
        border_mask[:, 0] = True  # Left
        border_mask[:, -1] = True  # Right
        
        inner_border = inner_region[border_mask]
        if len(inner_border) > 5:
            inner_border_pixels = inner_border

    # If inner margin sufficient, use it
    if inner_border_pixels is not None and len(inner_border_pixels) > 10:
        # Get the most common color in inner border
        inner_encoded = (
            inner_border_pixels[:, 0].astype(np.uint32)
            | (inner_border_pixels[:, 1].astype(np.uint32) << 8)
            | (inner_border_pixels[:, 2].astype(np.uint32) << 16)
        )
        unique, counts = np.unique(inner_encoded, return_counts=True)
        dominant_idx = np.argmax(counts)
        dominant = unique[dominant_idx]
        
        b = int(dominant & 0xFF)
        g = int((dominant >> 8) & 0xFF)
        r = int((dominant >> 16) & 0xFF)
        return (b, g, r)

    # Priority 2: Fall back to outer margin with outlier filtering
    ox1 = max(x - margin, 0)
    oy1 = max(y - margin, 0)
    ox2 = min(x + w + margin, img_w)
    oy2 = min(y + h + margin, img_h)

    outer = image_bgr[oy1:oy2, ox1:ox2].copy()
    if outer.size == 0:
        return (255, 255, 255)

    # Apply bilateral filtering to denoise
    if outer.shape[0] > 2 and outer.shape[1] > 2:
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

    # Calculate brightness for each pixel and filter outliers using IQR
    brightness = np.mean(border_pixels, axis=1)
    
    q1 = np.percentile(brightness, 25)
    q3 = np.percentile(brightness, 75)
    iqr = q3 - q1
    
    # Keep pixels within 1.5*IQR of the quartiles (standard outlier detection)
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    valid_mask = (brightness >= lower_bound) & (brightness <= upper_bound)
    filtered_pixels = border_pixels[valid_mask]

    if len(filtered_pixels) == 0:
        # If all filtered out, use median
        return tuple(np.median(border_pixels, axis=0).astype(int).tolist())

    # Find most common color among filtered pixels
    filtered_encoded = (
        filtered_pixels[:, 0].astype(np.uint32)
        | (filtered_pixels[:, 1].astype(np.uint32) << 8)
        | (filtered_pixels[:, 2].astype(np.uint32) << 16)
    )
    
    unique, counts = np.unique(filtered_encoded, return_counts=True)
    dominant_idx = np.argmax(counts)
    dominant = unique[dominant_idx]
    
    b = int(dominant & 0xFF)
    g = int((dominant >> 8) & 0xFF)
    r = int((dominant >> 16) & 0xFF)
    return (b, g, r)


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


def create_diff_image(original_path: Path, cleaned_path: Path) -> np.ndarray:
    """
    Create a difference/comparison image highlighting changes between original and cleaned.
    
    Color coding:
    - RED areas: Text that was removed (original content)
    - CYAN areas: Background that was filled/added
    - WHITE areas: No significant changes
    
    Returns the diff image as a numpy array
    """
    original = cv2.imread(str(original_path))
    cleaned = cv2.imread(str(cleaned_path))
    
    if original is None or cleaned is None:
        print("ERROR: Could not read one or both images for diff.")
        return None
    
    # Ensure both images have the same dimensions
    if original.shape != cleaned.shape:
        cleaned = cv2.resize(cleaned, (original.shape[1], original.shape[0]))
    
    # Convert to float for precise calculations
    original_f = original.astype(np.float32)
    cleaned_f = cleaned.astype(np.float32)
    
    # Calculate the absolute difference
    diff = np.abs(original_f - cleaned_f)
    
    # Create a color-coded diff visualization
    diff_image = np.zeros_like(original)
    
    # Threshold to identify significant changes (avoid noise)
    threshold = 15
    diff_mask = np.any(diff > threshold, axis=2)
    
    # Where original is darker than cleaned (text was removed) - show in RED
    removed = np.all(original_f < (cleaned_f - threshold), axis=2)
    diff_image[removed] = [0, 0, 255]  # Red in BGR
    
    # Where original is lighter than cleaned (background was filled) - show in CYAN  
    added = np.all(original_f > (cleaned_f + threshold), axis=2)
    diff_image[added] = [255, 255, 0]  # Cyan in BGR
    
    # Areas with changes but not clearly removed/added - show in MAGENTA
    mixed = diff_mask & ~removed & ~added
    diff_image[mixed] = [255, 0, 255]  # Magenta in BGR
    
    # Blend the diff visualization with the original for better visibility
    diff_viz = cv2.addWeighted(original, 0.6, diff_image, 0.4, 0)
    
    return diff_viz


def create_side_by_side(original_path: Path, cleaned_path: Path) -> np.ndarray:
    """
    Create a side-by-side comparison image with labels.
    
    Returns the side-by-side comparison as a numpy array
    """
    original = cv2.imread(str(original_path))
    cleaned = cv2.imread(str(cleaned_path))
    
    if original is None or cleaned is None:
        print("ERROR: Could not read one or both images for side-by-side.")
        return None
    
    # Ensure both images have the same dimensions
    if original.shape != cleaned.shape:
        cleaned = cv2.resize(cleaned, (original.shape[1], original.shape[0]))
    
    # Create side-by-side image
    h, w = original.shape[:2]
    side_by_side = np.hstack([original, cleaned])
    
    # Add labels on a background stripe
    label_height = 50
    side_by_side_labeled = np.ones((h + label_height, w * 2, 3), dtype=np.uint8) * 255
    side_by_side_labeled[label_height:, :] = side_by_side
    
    # Add labels with background
    cv2.rectangle(side_by_side_labeled, (0, 0), (w, label_height), (200, 200, 200), -1)
    cv2.rectangle(side_by_side_labeled, (w, 0), (w * 2, label_height), (200, 200, 200), -1)
    
    cv2.putText(side_by_side_labeled, "ORIGINAL", (20, 35), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    cv2.putText(side_by_side_labeled, "CLEANED", (w + 20, 35), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    
    return side_by_side_labeled

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
    text_boxes  = [obj for obj in all_objects if obj["object_type"] in ("text", "char")]

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

    # ── Create and save diff image ────────────────────────────────────────────
    print("Creating diff comparison image...")
    diff_image = create_diff_image(image_path, cleaned_path)
    
    if diff_image is not None:
        diff_path = OUTPUT_DIR / "text_cleanup_diff.png"
        cv2.imwrite(str(diff_path), diff_image)
        print(f"Saved : {diff_path}")
    else:
        print("WARNING: Failed to create diff image.")

    # ── Create and save side-by-side comparison ───────────────────────────────
    print("Creating side-by-side comparison...")
    side_by_side = create_side_by_side(image_path, cleaned_path)
    
    if side_by_side is not None:
        side_by_side_path = OUTPUT_DIR / "text_cleanup_comparison.png"
        cv2.imwrite(str(side_by_side_path), side_by_side)
        print(f"Saved : {side_by_side_path}")
    else:
        print("WARNING: Failed to create side-by-side comparison.")


if __name__ == "__main__":
    main()
