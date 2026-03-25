"""overlay_compare — simple visual overlay and diff utilities.

**Purpose:**
Provides convenience functions to create visual comparisons between reference
and rendered images. Intended as developer utilities for quick visual inspection
of alignment and layout changes during optimization.

**Functions:**

- **blend_overlay():** Alpha-blend rendered on top of original image
  - alpha=0.5 → 50% mix  
  - alpha=0.3 → mostly original with hint of rendered

- **side_by_side():** Juxtapose original and rendered at matching height
  - Optional labels ("ORIGINAL", "RENDERED")
  - Gray gap separator for clarity

- **diff_heatmap():** Pixel-level difference visualization
  - Red = large pixel differences
  - Dark/black = close matches
  - Useful for spotting layout shifts and rendering artifacts

**Outputs:**
- Blended png: blend_overlay.png
- Side-by-side: side_by_side.png
- Heatmap: diff_heatmap.png (in current output directory)

**Usage:**
    python pipeline/optimize/tools/overlay_compare.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
_ROOT = _HERE.parent

ORIGINAL_PATH = str(_ROOT / "image_reference" / "Page_1.png")
RENDERED_PATH = str(_ROOT / "image_reference" / "Output_1.png")
OUTPUT_DIR    = str(_HERE)

# ── Parameters ────────────────────────────────────────────────────────
BLEND_ALPHA  = 0.5   # 0.0 = only original, 1.0 = only rendered
LABEL_IMAGES = True  # draw labels on side-by-side output


def load_as_rgb(path):
    """Open any image format and convert to RGB color space.
    
    Args:
        path: Image file path (str or Path)
        
    Returns:
        PIL.Image: RGB image
    """
    return Image.open(path).convert("RGB")


def resize_to_match(img, reference):
    """Resize img to the same dimensions as reference using high-quality resampling.
    
    Args:
        img: PIL.Image to resize
        reference: PIL.Image reference for target dimensions
        
    Returns:
        PIL.Image: Resized image matching reference dimensions
    """
    return img.resize(reference.size, Image.LANCZOS)


def blend_overlay(original, rendered, alpha=0.5):
    """Alpha-blend rendered on top of original (PIL.Image.blend semantics).
    
    **Effect:**
    - alpha=0.0 → completely original
    - alpha=0.5 → equal mix (50/50)
    - alpha=1.0 → completely rendered
    
    Args:
        original: PIL.Image reference
        rendered: PIL.Image output
        alpha: Blend factor (0.0 to 1.0)
        
    Returns:
        PIL.Image: Blended image at original dimensions
    """
    rendered_r = resize_to_match(rendered, original)
    return Image.blend(original, rendered_r, alpha=alpha)


def side_by_side(original, rendered, gap=20, label=True):
    """Place original and rendered images side-by-side at matching height.
    
    Resizes rendered image to match original height, then tiles horizontally
    with optional gray gap separator and labels.
    
    Args:
        original: PIL.Image reference
        rendered: PIL.Image output (will be aspect-ratio-preserved resized)
        gap: Pixel width of separator between images (default 20)
        label: If True, draw "ORIGINAL" and "RENDERED" labels
        
    Returns:
        PIL.Image: Combined side-by-side image
    """
    # Match height
    h = original.height
    rendered_r = rendered.resize(
        (int(rendered.width * h / rendered.height), h), Image.LANCZOS
    )

    gap_strip = Image.new("RGB", (gap, h), (180, 180, 180))
    combined  = Image.new("RGB", (original.width + gap + rendered_r.width, h), (180, 180, 180))
    combined.paste(original,  (0, 0))
    combined.paste(gap_strip, (original.width, 0))
    combined.paste(rendered_r, (original.width + gap, 0))

    if label:
        draw = ImageDraw.Draw(combined)
        # Try to load a font; fall back to default
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except Exception:
            font = ImageFont.load_default()

        draw.rectangle([0, 0, 200, 40], fill=(0, 0, 0, 180))
        draw.text((10, 8), "ORIGINAL", fill=(255, 255, 255), font=font)

        rx = original.width + gap
        draw.rectangle([rx, 0, rx + 200, 40], fill=(30, 30, 180, 180))
        draw.text((rx + 10, 8), "RENDERED", fill=(255, 255, 255), font=font)

    return combined


def diff_heatmap(original, rendered):
    """Compute per-pixel absolute difference and render as a heatmap.
    
    **Visualization:**
    - Bright red: Large pixel-level differences (misalignment/changes)
    - Dark/black: Close matches (no difference)
    - Green tints: Intermediate differences
    
    **Use cases:**
    - Spot layout shifts (localized misalignment regions)
    - Identify rendering artifacts
    - Compare before/after optimization
    
    Args:
        original: PIL.Image reference
        rendered: PIL.Image output
        
    Returns:
        PIL.Image: Heatmap visualization at original dimensions
    """
    rendered_r = resize_to_match(rendered, original)

    orig_arr = np.array(original, dtype=np.float32)
    rend_arr = np.array(rendered_r, dtype=np.float32)

    diff = np.abs(orig_arr - rend_arr)          # shape (H, W, 3)
    diff_mean = diff.mean(axis=2)               # collapse channels → (H, W)

    # Normalise to 0-255
    diff_norm = (diff_mean / diff_mean.max() * 255).astype(np.uint8)

    # Colorise: low diff → dark blue, high diff → bright red
    r = diff_norm
    g = (255 - diff_norm) // 4
    b = 255 - diff_norm
    heatmap_arr = np.stack([r, g, b], axis=2).astype(np.uint8)
    heatmap = Image.fromarray(heatmap_arr, "RGB")

    # Overlay lightly on original for context
    combined = Image.blend(original, heatmap, alpha=0.55)

    # Stats
    total_pixels = diff_mean.size
    matched      = int((diff_mean < 10).sum())
    pct_matched  = matched / total_pixels * 100
    avg_diff     = diff_mean.mean()
    print(f"  Avg pixel diff : {avg_diff:.2f} / 255")
    print(f"  Pixels < 10 diff: {pct_matched:.1f}%  (near-perfect match)")

    return combined


def save(img, filename):
    path = Path(OUTPUT_DIR) / filename
    img.save(str(path))
    print(f"  Saved → {path}")
    return str(path)


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading images...")
    original = load_as_rgb(ORIGINAL_PATH)
    rendered = load_as_rgb(RENDERED_PATH)
    print(f"  Original : {original.size}")
    print(f"  Rendered : {rendered.size}")

    # 1. Blend overlay
    print("\n[1] Generating blend overlay (50%)...")
    blended = blend_overlay(original, rendered, alpha=BLEND_ALPHA)
    save(blended, "overlay_50.png")

    # 2. Side by side
    print("\n[2] Generating side-by-side comparison...")
    sbs = side_by_side(original, rendered, label=LABEL_IMAGES)
    save(sbs, "overlay_side_by_side.png")

    # 3. Diff heatmap
    print("\n[3] Generating difference heatmap...")
    heatmap = diff_heatmap(original, rendered)
    save(heatmap, "overlay_diff.png")

    print("\nDone! Three comparison images saved.")
