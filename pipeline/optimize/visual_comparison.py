#!/usr/bin/env python3
"""visual_comparison — comprehensive visual debugging artifacts.

**Purpose:**
Creates visual debugging artifacts comparing rendered output (Output_1.png)
against reference (Page_1.png). Multiple visualization techniques to inspect
alignment, identify mismatches, and verify optimization progress.

**Output artifacts (in generated/comparison/):**

1. **overlay_comparison.png:**
   - Color overlay: Red channel = rendered output, Green channel = reference
   - Magenta areas = perfect pixel alignment
   - Pure Red/Cyan/Green = misalignment regions (useful for spotting shifts)

2. **alpha_blend_*.png:**
   - Alpha-blended overlay with configurable transparency
   - Available at alphas: 0.3 (mostly reference), 0.5 (equal), 0.7 (mostly rendered)
   - Quick visual comparison without full side-by-side

3. **side_by_side_comparison.png:**
   - Horizontal juxtaposition of rendered (left) and reference (right)
   - Height-normalized, optional labels and separator
   - Best for detailed comparison

4. **difference_heatmap.png:**
   - Heatmap showing pixel-level differences overlaid on reference
   - Blue = similar, Red = different (colormap-based)
   - Includes statistics: min/mean/max pixel deviation

**Configurable options:**
- ALPHA_BLEND_FACTORS: Transparency levels for alpha blends (default: 0.3, 0.5, 0.7)
- HEATMAP_TARGET_HEIGHT: Preview height for side-by-side (default: 1200px)
- LABEL_IMAGES: Whether to draw labels on side-by-side (default: True)
- GAP_SEPARATOR: Pixel width between side-by-side images (default: 20px)

**Usage:**
    python pipeline/optimize/visual_comparison.py

**Inputs:**
- generated/Output_1.png (current rendered resume)
- source/references/Page_1.png (reference resume)

**Outputs:**
- generated/comparison/overlay_comparison.png
- generated/comparison/alpha_blend_30.png
- generated/comparison/alpha_blend_50.png
- generated/comparison/alpha_blend_70.png
- generated/comparison/side_by_side_comparison.png
- generated/comparison/difference_heatmap.png
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

# ────────────────────────────────────────────────────────────────────────────
# PATHS & CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent

OUTPUT_IMAGE = WORKSPACE / "generated" / "Output_1.png"
REFERENCE_IMAGE = WORKSPACE / "source" / "references" / "Page_1.png"
OUTPUT_DIR = WORKSPACE / "generated" / "comparison"

# Configurable options
ALPHA_BLEND_FACTORS = [0.3, 0.5, 0.7]  # Transparency levels for alpha blends
HEATMAP_TARGET_HEIGHT = 1200  # Preview height for side-by-side display
LABEL_IMAGES = True  # Draw labels on side-by-side output
GAP_SEPARATOR = 20  # Pixel width between side-by-side images

# ────────────────────────────────────────────────────────────────────────────
# VALIDITY CHECKS & HELPERS
# ────────────────────────────────────────────────────────────────────────────

def validate_inputs():
    """Check that both input images exist and are readable.
    
    Returns:
        bool: True if both images found, False otherwise
    """
    if not OUTPUT_IMAGE.exists():
        print(f"ERROR: Output image not found: {OUTPUT_IMAGE}")
        return False
    
    if not REFERENCE_IMAGE.exists():
        print(f"ERROR: Reference image not found: {REFERENCE_IMAGE}")
        return False
    
    return True


def load_as_rgb(path: Path) -> Image.Image:
    """Open any image format and convert to RGB color space.
    
    Args:
        path: Image file path
        
    Returns:
        PIL.Image: RGB image
    """
    return Image.open(str(path)).convert("RGB")


def resize_to_match(img: Image.Image, reference: Image.Image) -> Image.Image:
    """Resize img to the same dimensions as reference using high-quality resampling.
    
    Args:
        img: PIL.Image to resize
        reference: PIL.Image reference for target dimensions
        
    Returns:
        PIL.Image: Resized image matching reference dimensions
    """
    return img.resize(reference.size, Image.Resampling.LANCZOS)


# ────────────────────────────────────────────────────────────────────────────
# COMPARISON GENERATORS
# ────────────────────────────────────────────────────────────────────────────

def create_overlay_comparison():
    """Create color overlay showing pixel-level alignment.
    
    **Visualization:**
    - Red channel = Rendered output (Output_1)
    - Green channel = Reference (Page_1)
    - Magenta areas = Perfect pixel alignment
    - Pure Red/Cyan/Green = Misaligned regions
    
    **Interpretation:**
    - Magenta = output and reference pixels both bright (aligned text)
    - Red = output text where reference is blank (output too far right/down)
    - Green = reference text where output is blank (output too far left/up)
    - Black = both blank (good match)
    
    Returns:
        bool: True on success
    """
    print("[color-overlay] Loading images...")
    
    # Load as grayscale for overlay analysis
    output = cv2.imread(str(OUTPUT_IMAGE), cv2.IMREAD_GRAYSCALE)
    reference = cv2.imread(str(REFERENCE_IMAGE), cv2.IMREAD_GRAYSCALE)
    
    if output is None or reference is None:
        print("ERROR: Failed to load images for overlay")
        return False
    
    # Ensure same size
    h, w = reference.shape
    output = cv2.resize(output, (w, h))
    
    print(f"[color-overlay] Image size: {w}×{h}")
    
    # Create 3-channel image for color overlay
    # Red = rendered output, Green = reference
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    overlay[:, :, 0] = output        # Blue channel (will become red in BGR)
    overlay[:, :, 1] = reference     # Green channel
    overlay[:, :, 2] = output        # Red channel (will become blue in BGR)
    
    # Convert BGR to RGB for correct colors
    overlay_rgb = cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB)
    
    result = Image.fromarray(overlay_rgb)
    output_path = OUTPUT_DIR / "overlay_comparison.png"
    result.save(output_path)
    
    print(f"[color-overlay] Saved → {output_path.name}")
    print(f"[color-overlay] Legend: Magenta = perfect alignment, Red/Cyan = misalignment")
    return True


def create_alpha_blends():
    """Create alpha-blended overlays at multiple transparency levels.
    
    **Effect:**
    - alpha=0.3 → mostly reference with hint of rendered (30% rendered)
    - alpha=0.5 → equal 50/50 mix
    - alpha=0.7 → mostly rendered with hint of reference (70% rendered)
    
    Returns:
        bool: True on success
    """
    print("[alpha-blend] Loading images...")
    
    reference = load_as_rgb(REFERENCE_IMAGE)
    rendered = load_as_rgb(OUTPUT_IMAGE)
    
    if reference is None or rendered is None:
        print("ERROR: Failed to load images for alpha blend")
        return False
    
    # Ensure same size
    rendered_resized = resize_to_match(rendered, reference)
    
    all_ok = True
    for alpha in ALPHA_BLEND_FACTORS:
        try:
            # Blend: (1-alpha)*reference + alpha*rendered
            blended = Image.blend(reference, rendered_resized, alpha=alpha)
            alpha_int = int(alpha * 100)
            output_path = OUTPUT_DIR / f"alpha_blend_{alpha_int}.png"
            blended.save(output_path)
            print(f"[alpha-blend] Saved α={alpha:.1%} → {output_path.name}")
        except Exception as e:
            print(f"[alpha-blend] ERROR at α={alpha:.1%}: {e}")
            all_ok = False
    
    return all_ok

def create_side_by_side():
    """Create side-by-side comparison with optional labels and separator.
    
    Resizes rendered image to match reference height, then tiles horizontally
    with optional gray gap separator and labels.
    
    Returns:
        bool: True on success
    """
    print("[side-by-side] Loading images...")
    
    reference = load_as_rgb(REFERENCE_IMAGE)
    rendered = load_as_rgb(OUTPUT_IMAGE)
    
    if reference is None or rendered is None:
        print("ERROR: Failed to load images for side-by-side")
        return False
    
    # Resize rendered to match reference height (maintain aspect ratio)
    h = reference.height
    scale = h / rendered.height
    rendered_r = rendered.resize(
        (int(rendered.width * scale), h),
        Image.Resampling.LANCZOS
    )
    
    print(f"[side-by-side] Resized to height: {h}, scale: {scale:.2f}")
    
    # Create canvas with gap
    total_width = reference.width + GAP_SEPARATOR + rendered_r.width
    gap_color = (200, 200, 200)  # Light gray
    canvas = Image.new("RGB", (total_width + 60, h + 60), "white")
    
    # Paste images
    canvas.paste(reference, (10, 50))
    gap_strip = Image.new("RGB", (GAP_SEPARATOR, h), gap_color)
    canvas.paste(gap_strip, (reference.width + 10, 50))
    canvas.paste(rendered_r, (reference.width + GAP_SEPARATOR + 10, 50))
    
    # Add labels if requested
    if LABEL_IMAGES:
        draw = ImageDraw.Draw(canvas)
        
        # Try to load a decent font; fall back to default
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24
            )
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
        
        # Reference label
        draw.rectangle([5, 10, 250, 45], fill=(0, 0, 0))
        if font:
            draw.text((12, 15), "REFERENCE", fill=(255, 255, 255), font=font)
        else:
            draw.text((12, 15), "REFERENCE", fill=(255, 255, 255))
        
        # Rendered label
        rx = reference.width + GAP_SEPARATOR + 10
        draw.rectangle([rx, 10, rx + 250, 45], fill=(100, 100, 150))
        if font:
            draw.text((rx + 12, 15), "RENDERED", fill=(255, 255, 255), font=font)
        else:
            draw.text((rx + 12, 15), "RENDERED", fill=(255, 255, 255))
    
    output_path = OUTPUT_DIR / "side_by_side_comparison.png"
    canvas.save(output_path)
    
    print(f"[side-by-side] Saved → {output_path.name}")
    print(f"[side-by-side] Size: {canvas.width}×{canvas.height}")
    return True

def create_diff_heatmap():
    """Create difference heatmap showing pixel-level variations.
    
    **Visualization:**
    - Overlaid on reference image for context
    - Blue regions = similar (close match)
    - Red regions = different (misalignment)
    - Green = intermediate differences
    
    Includes statistics: min, mean, max pixel deviation and % of near-perfect matches.
    
    Returns:
        bool: True on success
    """
    print("[diff-heatmap] Loading images...")
    
    reference = load_as_rgb(REFERENCE_IMAGE)
    rendered = load_as_rgb(OUTPUT_IMAGE)
    
    if reference is None or rendered is None:
        print("ERROR: Failed to load images for diff")
        return False
    
    # Resize rendered to match reference
    rendered_r = resize_to_match(rendered, reference)
    
    # Convert to numpy arrays
    orig_arr = np.array(reference, dtype=np.float32)
    rend_arr = np.array(rendered_r, dtype=np.float32)
    
    # Compute per-pixel absolute difference
    diff = np.abs(orig_arr - rend_arr)  # shape (H, W, 3)
    diff_mean = diff.mean(axis=2)  # collapse channels → (H, W)
    
    # Normalize to 0-255
    diff_normalized = (diff_mean / diff_mean.max() * 255).astype(np.uint8)
    
    # Colorize: low diff → dark blue, high diff → bright red (reverse of intuition)
    r = diff_normalized
    g = (255 - diff_normalized) // 4
    b = 255 - diff_normalized
    heatmap_arr = np.stack([r, g, b], axis=2).astype(np.uint8)
    heatmap_pil = Image.fromarray(heatmap_arr, "RGB")
    
    # Blend heatmap with reference for context
    combined = Image.blend(reference, heatmap_pil, alpha=0.55)
    
    output_path = OUTPUT_DIR / "difference_heatmap.png"
    combined.save(output_path)
    
    # Compute and print statistics
    total_pixels = diff_mean.size
    matched = int((diff_mean < 10).sum())
    pct_matched = matched / total_pixels * 100
    avg_diff = diff_mean.mean()
    max_diff = diff_mean.max()
    min_diff = diff_mean.min()
    
    print(f"[diff-heatmap] Saved → {output_path.name}")
    print(f"[diff-heatmap] Statistics:")
    print(f"  Min pixel diff   : {min_diff:.1f} / 255")
    print(f"  Mean pixel diff  : {avg_diff:.1f} / 255")
    print(f"  Max pixel diff   : {max_diff:.1f} / 255")
    print(f"  Pixels < 10 diff : {pct_matched:.1f}%  (near-perfect matches)")
    print(f"[diff-heatmap] Legend: Blue = similar, Red = different")
    
    return True

def main():
    """Generate visual comparison artifacts (overlay, side-by-side, heatmap).
    
    Creates three visualizations comparing Output_1.png (rendered) vs Page_1.png
    (reference) to inspect alignment and identify rendering issues.
    
    **Outputs:**
    1. overlay_comparison.png - Red/Green overlay (red=rendered, green=reference)
    2. side_by_side_comparison.png - Horizontal juxtaposition with labels
    3. difference_heatmap.png - Pixel-level difference heatmap (red=high diff)
    
    All files saved to generated/comparison/.
    """
    
    if not validate_inputs():
        return 1
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Output image:    {OUTPUT_IMAGE.name}")
    print(f"Reference image: {REFERENCE_IMAGE.name}")
    print(f"Output path:     {OUTPUT_DIR.relative_to(WORKSPACE)}/")
    print(f"Alpha blends:    {', '.join(f'{int(a*100)}%' for a in ALPHA_BLEND_FACTORS)}\n")
    
    all_ok = True
    
    # 1. Color overlay (red/green channels)
    try:
        print("[1/5] Color overlay (Red=rendered, Green=reference)…")
        all_ok &= create_overlay_comparison()
        print()
    except Exception as e:
        print(f"ERROR in color overlay: {e}\n")
        all_ok = False
    
    # 2. Alpha blends (multiple transparency levels)
    try:
        print("[2/5] Alpha-blended overlays…")
        all_ok &= create_alpha_blends()
        print()
    except Exception as e:
        print(f"ERROR in alpha blends: {e}\n")
        all_ok = False
    
    # 3. Side-by-side comparison
    try:
        print("[3/5] Side-by-side comparison…")
        all_ok &= create_side_by_side()
        print()
    except Exception as e:
        print(f"ERROR in side-by-side: {e}\n")
        all_ok = False
    
    # 4. Difference heatmap
    try:
        print("[4/5] Pixel-level difference heatmap…")
        all_ok &= create_diff_heatmap()
        print()
    except Exception as e:
        print(f"ERROR in diff: {e}\n")
        all_ok = False
    
    print("=" * 70)
    if all_ok:
        print("✓ All comparisons complete")
        print("=" * 70 + "\n")
        return 0
    else:
        print("✗ Some comparisons failed")
        print("=" * 70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
