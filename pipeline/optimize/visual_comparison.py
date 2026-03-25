#!/usr/bin/env python3
"""
Visual Comparison Tool — Generate diff and overlay images
Compares rendered Output_1.png against reference Page_1.png

Creates:
1. overlay_comparison.png — Animated-style layers showing alignment
2. side_by_side_comparison.png — Direct visual comparison
3. diff_heatmap.png — Highlighting differences via color intensity
"""

import sys
from pathlib import Path
import numpy as np
from PIL import Image
import cv2

# ────────────────────────────────────────────────────────────────────────────
# PATHS
# ────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent.parent

OUTPUT_IMAGE = WORKSPACE / "generated" / "Output_1.png"
REFERENCE_IMAGE = WORKSPACE / "source" / "references" / "Page_1.png"
OUTPUT_DIR = WORKSPACE / "generated" / "comparison"

# ────────────────────────────────────────────────────────────────────────────
# VALIDITY CHECKS
# ────────────────────────────────────────────────────────────────────────────

def validate_inputs():
    """Check that both input images exist"""
    if not OUTPUT_IMAGE.exists():
        print(f"ERROR: Output image not found: {OUTPUT_IMAGE}")
        return False
    
    if not REFERENCE_IMAGE.exists():
        print(f"ERROR: Reference image not found: {REFERENCE_IMAGE}")
        return False
    
    return True

# ────────────────────────────────────────────────────────────────────────────
# COMPARISON GENERATORS
# ────────────────────────────────────────────────────────────────────────────

def create_overlay_comparison():
    """
    Create overlay showing alignment between rendered and reference.
    Red channel = Output_1, Green channel = Page_1
    Magenta areas = perfect alignment, Cyan/Red/Green = misalignment
    """
    print("[overlay] Loading images...")
    
    # Load as grayscale for overlay analysis
    output = cv2.imread(str(OUTPUT_IMAGE), cv2.IMREAD_GRAYSCALE)
    reference = cv2.imread(str(REFERENCE_IMAGE), cv2.IMREAD_GRAYSCALE)
    
    if output is None or reference is None:
        print("ERROR: Failed to load images for overlay")
        return False
    
    # Ensure same size
    h, w = reference.shape
    output = cv2.resize(output, (w, h))
    
    print(f"[overlay] Image size: {w}×{h}")
    
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
    
    print(f"[overlay] Saved → {output_path.name}")
    print(f"[overlay] Legend: Magenta = perfect alignment, Red/Cyan = misalignment")
    return True

def create_side_by_side():
    """
    Create side-by-side comparison with labels
    """
    print("[side-by-side] Loading images...")
    
    output = Image.open(OUTPUT_IMAGE)
    reference = Image.open(REFERENCE_IMAGE)
    
    # Resize to same height for comparison
    h_target = 1200  # Reasonable height for display
    scale_o = h_target / output.height
    scale_r = h_target / reference.height
    
    output = output.resize((int(output.width * scale_o), h_target), Image.Resampling.LANCZOS)
    reference = reference.resize((int(reference.width * scale_r), h_target), Image.Resampling.LANCZOS)
    
    print(f"[side-by-side] Resized to height: {h_target}")
    
    # Create canvas
    total_width = output.width + reference.width + 40  # 20px padding each side
    canvas = Image.new("RGB", (total_width, h_target + 60), "white")
    
    # Paste images
    canvas.paste(output, (10, 50))
    canvas.paste(reference, (output.width + 30, 50))
    
    # Add labels (simple text)
    try:
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(canvas)
        
        # Try to use default font
        try:
            font = ImageFont.load_default()
        except:
            font = None
        
        draw.text((output.width // 2 - 50, 10), "Rendered (Output_1)", fill="black", font=font)
        draw.text((output.width + reference.width // 2 - 30, 10), "Reference (Page_1)", fill="black", font=font)
    except Exception as e:
        print(f"[side-by-side] Note: Could not add labels ({e})")
    
    output_path = OUTPUT_DIR / "side_by_side_comparison.png"
    canvas.save(output_path)
    
    print(f"[side-by-side] Saved → {output_path.name}")
    print(f"[side-by-side] Size: {total_width}×{h_target + 60}")
    return True

def create_diff_heatmap():
    """
    Create difference heatmap showing pixel-level variations.
    Brighter = more different, Darker = more similar
    """
    print("[diff-heatmap] Loading images...")
    
    # Load as grayscale
    output = cv2.imread(str(OUTPUT_IMAGE), cv2.IMREAD_GRAYSCALE)
    reference = cv2.imread(str(REFERENCE_IMAGE), cv2.IMREAD_GRAYSCALE)
    
    if output is None or reference is None:
        print("ERROR: Failed to load images for diff")
        return False
    
    # Resize to same size
    h, w = reference.shape
    output = cv2.resize(output, (w, h))
    
    # Compute absolute difference
    diff = cv2.absdiff(output, reference)
    
    # Apply Gaussian blur to smooth noise
    diff_smooth = cv2.GaussianBlur(diff, (5, 5), 0)
    
    # Normalize to 0-255 and invert (so similar areas are dark)
    diff_normalized = 255 - diff_smooth
    
    # Apply colormap (heatmap)
    heatmap = cv2.applyColorMap(diff_normalized, cv2.COLORMAP_JET)
    
    # Convert BGR to RGB
    heatmap_rgb = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
    
    result = Image.fromarray(heatmap_rgb)
    output_path = OUTPUT_DIR / "diff_heatmap.png"
    result.save(output_path)
    
    # Compute statistics
    diff_mean = np.mean(diff)
    diff_max = np.max(diff)
    diff_min = np.min(diff)
    
    print(f"[diff-heatmap] Saved → {output_path.name}")
    print(f"[diff-heatmap] Statistics: min={diff_min:.1f}, mean={diff_mean:.1f}, max={diff_max:.1f}")
    print(f"[diff-heatmap] Legend: Blue = similar, Red = different")
    return True

# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("Visual Comparison Tool")
    print("=" * 70 + "\n")
    
    if not validate_inputs():
        return 1
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"Output image:    {OUTPUT_IMAGE.name}")
    print(f"Reference image: {REFERENCE_IMAGE.name}")
    print(f"Output path:     {OUTPUT_DIR.relative_to(WORKSPACE)}/\n")
    
    all_ok = True
    
    try:
        all_ok &= create_overlay_comparison()
    except Exception as e:
        print(f"ERROR in overlay: {e}")
        all_ok = False
    
    try:
        all_ok &= create_side_by_side()
    except Exception as e:
        print(f"ERROR in side-by-side: {e}")
        all_ok = False
    
    try:
        all_ok &= create_diff_heatmap()
    except Exception as e:
        print(f"ERROR in diff: {e}")
        all_ok = False
    
    print("\n" + "=" * 70)
    if all_ok:
        print("✓ Comparison complete")
        print("=" * 70 + "\n")
        return 0
    else:
        print("✗ Some comparisons failed")
        print("=" * 70 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
