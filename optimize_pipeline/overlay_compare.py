"""
overlay_compare.py
------------------
Overlays the rendered resume screenshot on top of the original image
to visually compare alignment, spacing, and layout accuracy.

Usage:
    python overlay_compare.py

Outputs:
    overlay_50.png        — 50% blend (default comparison view)
    overlay_side_by_side.png — original | rendered side by side
    overlay_diff.png      — pixel-level difference heatmap
"""

from PIL import Image, ImageChops, ImageFilter, ImageDraw, ImageFont
import numpy as np
import os

# ── Paths ─────────────────────────────────────────────────────────────
ORIGINAL_PATH   = "Page_1.png"           # original reference image
RENDERED_PATH   = "resume_screenshot.png" # your rendered webpage PNG
OUTPUT_DIR      = "."                     # where to save outputs

# ── Parameters ────────────────────────────────────────────────────────
BLEND_ALPHA     = 0.5   # 0.0 = only original, 1.0 = only rendered
RESIZE_TO_ORIG  = True  # if True, scale rendered to match original size
LABEL_IMAGES    = True  # draw labels on side-by-side output


def load_as_rgb(path):
    """Open any image and convert to RGB."""
    return Image.open(path).convert("RGB")


def resize_to_match(img, reference):
    """Resize img to the same dimensions as reference using high-quality resampling."""
    return img.resize(reference.size, Image.LANCZOS)


def blend_overlay(original, rendered, alpha=0.5):
    """
    Alpha-blend rendered on top of original.
    alpha=0.5 → equal mix; alpha=0.3 → mostly original.
    """
    rendered_r = resize_to_match(rendered, original)
    return Image.blend(original, rendered_r, alpha=alpha)


def side_by_side(original, rendered, gap=20, label=True):
    """Place original and rendered next to each other at the same height."""
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
    """
    Compute per-pixel absolute difference and render as a heatmap.
    Bright red = large difference, dark = close match.
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
    path = os.path.join(OUTPUT_DIR, filename)
    img.save(path)
    print(f"  Saved → {path}")
    return path


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
