#!/usr/bin/env python3
"""ocr.utils — shared helpers and I/O utilities for OCR pipeline scripts.

**Purpose:**
Provides centralized utilities for all OCR extraction and annotation scripts.
Handles workspace configuration, CSV I/O, image discovery, text normalization,
color estimation, and bounding-box overlap calculations.

**Key components:**

**Workspace Configuration:**
- Image path resolution (source/references/Page_1.png or IMAGE_PATH env var)
- Temp directory for generated content tokens
- CSV field names for objects data

**CSV I/O:**
- read_csv_objects() / write_csv_objects() with w/h ↔ width/height conversion
- update_csv_objects() for selective row replacement by object_type

**Image Discovery:**
- find_image() with multi-strategy lookup (env var → default → legacy)
- get_image_output_dir() / get_output_csv() for per-image output paths
- ensure_output_dir() for safe directory creation

**Text Processing:**
- normalize_text() to standardize dash variants and Unicode characters
- load_reference_words() / load_reference_order() for content.txt tokens

**Spatial Analysis:**
- coverage() for bounding-box overlap fraction calculations
- overlaps_text() to filter structural elements overlapping text regions
- estimate_colors() for foreground/background color extraction

**Color Utilities:**
- bgr_to_hex() for BGR ↔ #RRGGBB conversion
- _dominant_color() for finding most-frequent pixels
- IQR outlier filtering for robust color estimation with denoising
"""

import csv
import os
from pathlib import Path

import numpy as np

# ── Configuration ──────────────────────────────────────────────────────────────
# Workspace root = 3 levels up from ocr_pipeline/ package directory
SCRIPT_DIR = Path(__file__).parent.parent.parent.resolve()
IMAGE_DIR = SCRIPT_DIR / "source" / "references"
TEMP_DIR = SCRIPT_DIR / "generated" / "temp"
IMAGE_FILE = "Page_1.png"
CONTENT_FILE = "content.txt"

# OpenCV BGR colours
GREEN = (0, 255, 0)  # matched text
RED = (0, 0, 255)  # unmatched text
BLUE = (255, 0, 0)  # structural objects

CSV_FIELDNAMES = ["object_type", "text", "x", "y", "width", "height", "color", "bg_color"]


# ── Output directory ──────────────────────────────────────────────────────────


def get_image_output_dir(image_path: Path | None = None) -> Path:
    """Get the output directory for a given image.
    
    Uses per-image stem-based subdirectories so multiple images can be processed
    independently. Example: Page_1.png → generated/ocr/Page_1/
    
    Args:
        image_path: Path to input image. If None, uses find_image() to locate it.
        
    Returns:
        Path to generated/ocr/{image_stem}/ directory (not created here)
    """
    if image_path is None:
        image_path = find_image()
    image_stem = image_path.stem  # filename without extension
    return SCRIPT_DIR / "generated" / "ocr" / image_stem


def get_output_csv(image_path: Path | None = None) -> Path:
    """Get the objects.csv path for a given image.
    
    Args:
        image_path: Path to input image. If None, uses find_image().
        
    Returns:
        Path to generated/ocr/{image_stem}/objects.csv
    """
    output_dir = get_image_output_dir(image_path)
    return output_dir / "objects.csv"


def ensure_output_dir(image_path: Path | None = None) -> None:
    """Create the output directory for a given image (generated/ocr/{image_stem}/).
    
    Creates parent directories as needed with mkdir(parents=True, exist_ok=True).
    
    Args:
        image_path: Path to input image. If None, uses find_image().
    """
    output_dir = get_image_output_dir(image_path)
    output_dir.mkdir(parents=True, exist_ok=True)


# ── Image discovery ────────────────────────────────────────────────────────────


def find_image() -> Path:
    """Locate the input PNG in image_reference/.

    Resolution order:
      1. IMAGE_PATH environment variable (set by pipeline.sh for multi-image runs)
      2. image_reference/Page_1.png  (default single-image name)
      3. First image_reference/*.png whose name starts with 'page' (legacy fallback)
    """
    env_path = os.environ.get("IMAGE_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        raise FileNotFoundError(
            f"IMAGE_PATH env var points to non-existent file: '{env_path}'"
        )
    direct = IMAGE_DIR / IMAGE_FILE
    if direct.exists():
        return direct
    for p in sorted(IMAGE_DIR.iterdir()):
        if p.suffix.lower() == ".png" and p.name.lower().startswith("page"):
            return p
    raise FileNotFoundError(
        f"No suitable PNG found in {IMAGE_DIR}. Expected '{IMAGE_FILE}'."
    )


# ── Text normalisation ─────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Normalize text by converting Unicode dash variants to ASCII hyphen.
    
    Replaces en-dash, em-dash, minus sign, and other dash Unicode characters
    with regular ASCII hyphen '-'. Used for consistent token matching across
    different markdown and OCR sources.
    
    Args:
        text: Text string potentially containing Unicode dashes
        
    Returns:
        Normalized text with all dashes converted to '-'
    """
    dash_variants = {
        "\u2013": "-",  # en-dash
        "\u2014": "-",  # em-dash
        "\u2212": "-",  # minus sign
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2043": "-",  # hyphen bullet
    }
    for dash, hyphen in dash_variants.items():
        text = text.replace(dash, hyphen)
    return text


# ── Content path helpers ──────────────────────────────────────────────────────


def get_content_path() -> Path:
    """Return the path to content.txt in the temp/ folder.
    
    Validates that the file exists (generated by extract_values.py).
    
    Returns:
        Path to generated/temp/content.txt
        
    Raises:
        FileNotFoundError if content.txt does not exist
    """
    path = TEMP_DIR / CONTENT_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"ERROR: '{CONTENT_FILE}' not found in {TEMP_DIR}.\n"
            "Run html_pipeline/extract_values.py first to generate it."
        )
    return path


# ── Reference word helpers ─────────────────────────────────────────────────────


def load_reference_words(path: Path | None = None) -> set[str]:
    """Load reference tokens from content.txt as a set of normalized strings.
    
    Creates two levels of tokenization:
    - Each full line (e.g., "John Doe") added as one token
    - Each whitespace-separated word added individually (e.g., "John", "Doe")
    
    This dual-level approach improves matching flexibility for OCR text validation.
    Uses normalize_text() to ensure consistency with OCR output.
    
    Args:
        path: Path to content.txt. If None, loads from generated/temp/content.txt
        
    Returns:
        set[str]: All normalized tokens (full lines and individual words)
    """
    if path is None:
        path = get_content_path()
    words: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = normalize_text(raw.strip())
            if not line:
                continue
            words.add(line)
            for token in line.split():
                words.add(token)
    return words


def load_reference_order(path: Path) -> list[str]:
    """Load normalized lines from content.txt preserving file order.
    
    Maintains the exact reading order of lines for downstream text object
    ordering by content.txt sequence. Useful for ensuring OCR detections
    are reordered to match the logical content order.
    
    Args:
        path: Path to content.txt file
        
    Returns:
        list[str]: Normalized lines in file order (empty lines skipped)
    """
    order = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = normalize_text(raw.strip())
            if line:
                order.append(line)
    return order


# ── Bounding-box helpers ───────────────────────────────────────────────────────


def coverage(b1: tuple, b2: tuple) -> float:
    """Return the fraction of box b1 that is covered by box b2.

    Computes intersection-over-union style metric for determining if two
    bounding boxes overlap significantly. Used to filter structural elements
    that overlap detected text regions.
    
    Args:
        b1: Bounding box (x, y, w, h) to measure coverage of
        b2: Bounding box (x, y, w, h) that may cover b1
        
    Returns:
        float: Fraction of b1 covered by b2 (0.0 to 1.0)
    """
    ix1 = max(b1[0], b2[0])
    iy1 = max(b1[1], b2[1])
    ix2 = min(b1[0] + b1[2], b2[0] + b2[2])
    iy2 = min(b1[1] + b1[3], b2[1] + b2[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area1 = b1[2] * b1[3]
    return inter / area1 if area1 > 0 else 0.0


def overlaps_text(
    x: int,
    y: int,
    w: int,
    h: int,
    text_boxes: list,
    threshold: float = 0.25,
) -> bool:
    """Return True if the given box overlaps any text box beyond the threshold.
    
    Checks if a bounding box (typically a structural element) significantly
    overlaps with any detected text region. Used to filter out structural
    contours that are actually parts of text.
    
    Args:
        x, y, w, h: Bounding box coordinates and dimensions
        text_boxes: List of text object dicts with keys 'x', 'y', 'w', 'h'
        threshold: Minimum coverage fraction to consider overlap (default 0.25 = 25%)
        
    Returns:
        bool: True if box overlaps any text box beyond threshold
    """
    for tb in text_boxes:
        if coverage((x, y, w, h), (tb["x"], tb["y"], tb["w"], tb["h"])) > threshold:
            return True
    return False


# ── CSV I/O ────────────────────────────────────────────────────────────────────


def read_csv_objects(csv_path: Path) -> list[dict]:
    """Read all rows from the objects CSV.
    
    Deserializes bounding box data from CSV format into Python dicts,
    converting width/height CSV fields to internal w/h notation.

    Args:
        csv_path: Path to objects.csv file
        
    Returns:
        list[dict]: Objects with keys: object_type, text, x, y, w, h, color, bg_color.
        Returns empty list if file does not exist.
    """
    if not csv_path.exists():
        return []
    objects = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            objects.append(
                {
                    "object_type": row["object_type"],
                    "text": row["text"],
                    "x": int(row["x"]),
                    "y": int(row["y"]),
                    "w": int(row["width"]),
                    "h": int(row["height"]),
                    "color": row.get("color", ""),
                    "bg_color": row.get("bg_color", ""),
                }
            )
    return objects


def write_csv_objects(objects: list[dict], csv_path: Path) -> None:
    """Write a list of object dicts (with w/h keys) to the CSV.
    
    Serializes Python object dicts to CSV format, converting internal w/h
    notation to CSV width/height column names.
    
    Args:
        objects: List of object dicts with w/h keys
        csv_path: Output CSV path (parent directories must exist)
    """
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for obj in objects:
            writer.writerow(
                {
                    "object_type": obj["object_type"],
                    "text": obj.get("text", ""),
                    "x": obj["x"],
                    "y": obj["y"],
                    "width": obj["w"],
                    "height": obj["h"],
                    "color": obj.get("color", ""),
                    "bg_color": obj.get("bg_color", ""),
                }
            )


# ── Colour extraction helpers ─────────────────────────────────────────────────


def bgr_to_hex(bgr: tuple) -> str:
    """Convert a BGR tuple to a hex colour string ``#RRGGBB``."""
    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    return f"#{r:02X}{g:02X}{b:02X}"


def _dominant_color(pixels: np.ndarray) -> tuple:
    """Return the most frequent BGR colour in a (N, 3) uint8 pixel array.
    
    Used internally for efficient color estimation by finding the mode of
    pixel values across a region using numpy encoding/decoding.
    
    Args:
        pixels: 2D array of shape (N, 3) with uint8 BGR values
        
    Returns:
        tuple: (B, G, R) color values as unsigned integers
    """
    encoded = (
        pixels[:, 0].astype(np.uint32)
        | (pixels[:, 1].astype(np.uint32) << 8)
        | (pixels[:, 2].astype(np.uint32) << 16)
    )
    unique, counts = np.unique(encoded, return_counts=True)
    dominant = unique[np.argmax(counts)]
    return (
        int(dominant & 0xFF),
        int((dominant >> 8) & 0xFF),
        int((dominant >> 16) & 0xFF),
    )


def estimate_colors(
    image_bgr: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    margin: int = 8,
    fg_threshold: float = 30.0,
) -> tuple[str, str]:
    """Estimate foreground (color) and background (bg_color) for a bounding box.
    
    **Strategy:**
    1. Sample outer-margin pixels (with IQR outlier filtering for robustness)
    2. Use dominant color of margin as background estimate
    3. Find interior pixels that differ from background by fg_threshold
    4. Use dominant color of those pixels as foreground
    5. Apply bilateral denoising if margin is large enough
    
    Background color is usually the document background. Foreground is the
    text/object color. Both are detected by frequency analysis.

    Args:
        image_bgr: OpenCV image array (uint8 BGR)
        x, y, w, h: Bounding box for color estimation
        margin: Pixel distance around box edge for background sampling (default 8)
        fg_threshold: Euclidean distance threshold to consider pixel as foreground (default 30)

    Returns:
        tuple[str, str]: (color_hex, bg_color_hex) both as "#RRGGBB" strings
    """
    img_h, img_w = image_bgr.shape[:2]

    # ── Background ────────────────────────────────────────────────────────────
    ox1, oy1 = max(x - margin, 0), max(y - margin, 0)
    ox2, oy2 = min(x + w + margin, img_w), min(y + h + margin, img_h)
    outer = image_bgr[oy1:oy2, ox1:ox2]

    inner_mask = np.zeros(outer.shape[:2], dtype=bool)
    r0 = max(y - oy1, 0)
    r1 = min(y - oy1 + h, outer.shape[0])
    c0 = max(x - ox1, 0)
    c1 = min(x - ox1 + w, outer.shape[1])
    inner_mask[r0:r1, c0:c1] = True

    border_pixels = outer[~inner_mask].reshape(-1, 3)
    if len(border_pixels) > 0:
        brightness = np.mean(border_pixels, axis=1)
        q1, q3 = np.percentile(brightness, 25), np.percentile(brightness, 75)
        iqr = q3 - q1
        valid = (brightness >= q1 - 1.5 * iqr) & (brightness <= q3 + 1.5 * iqr)
        filtered = border_pixels[valid] if valid.any() else border_pixels
        bg_bgr = _dominant_color(filtered)
    else:
        bg_bgr = (255, 255, 255)

    # ── Foreground ────────────────────────────────────────────────────────────
    ix1, iy1 = max(x, 0), max(y, 0)
    ix2, iy2 = min(x + w, img_w), min(y + h, img_h)

    if ix2 > ix1 and iy2 > iy1:
        inner = image_bgr[iy1:iy2, ix1:ix2].reshape(-1, 3)
        bg_arr = np.array(bg_bgr, dtype=np.float32)
        dists = np.linalg.norm(inner.astype(np.float32) - bg_arr, axis=1)
        fg_pixels = inner[dists > fg_threshold]
        fg_bgr = _dominant_color(fg_pixels) if len(fg_pixels) > 0 else bg_bgr
    else:
        fg_bgr = (0, 0, 0)

    return bgr_to_hex(fg_bgr), bgr_to_hex(bg_bgr)


def update_csv_objects(
    new_objects: list[dict], object_type: str, csv_path: Path
) -> None:
    """Replace all rows of the given object_type in the CSV with new_objects.
    
    **Merge strategy:**
    - Preserves all rows with object_type != the specified type
    - Deletes all old rows with the matching object_type
    - Appends all new_objects at the end
    - Creates CSV with headers if file does not exist
    
    Used to incrementally build CSV: first text objects, then structural,
    then characters without overwriting previous entries.

    Args:
        new_objects: List of object dicts to insert (with object_type field)
        object_type: Object type string to replace (e.g., "text", "structural")
        csv_path: Path to objects.csv (created if needed)
    """
    existing = read_csv_objects(csv_path) if csv_path.exists() else []
    kept = [o for o in existing if o["object_type"] != object_type]
    write_csv_objects(kept + new_objects, csv_path)
