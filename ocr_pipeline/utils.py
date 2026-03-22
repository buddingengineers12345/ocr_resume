#!/usr/bin/env python3
"""
utils.py
========
Shared configuration, helpers, and I/O utilities for the OCR pipeline.

SCRIPT_DIR points to the workspace root (parent of this package directory)
so that all scripts locate images and CSV files consistently regardless of
how or where they are invoked.
"""

import csv
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
# Workspace root = parent of the ocr_pipeline/ package directory
SCRIPT_DIR = Path(__file__).parent.parent.resolve()
IMAGE_DIR = SCRIPT_DIR / "image_reference"
TEMP_DIR = SCRIPT_DIR / "temp"
OUTPUT_DIR = SCRIPT_DIR / "output"
IMAGE_FILE = "Page_1.png"
CONTENT_FILE = "content.txt"
OUTPUT_CSV = OUTPUT_DIR / "objects.csv"

# OpenCV BGR colours
GREEN = (0, 255, 0)  # matched text
RED = (0, 0, 255)  # unmatched text
BLUE = (255, 0, 0)  # structural objects

CSV_FIELDNAMES = ["object_type", "text", "x", "y", "width", "height"]


# ── Output directory ──────────────────────────────────────────────────────────


def ensure_output_dir() -> None:
    """Create the output directory if it does not exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Image discovery ────────────────────────────────────────────────────────────


def find_image() -> Path:
    """Locate the input PNG in image_reference/; falls back to any page*.png."""
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
    """Replace dash variants (en-dash, em-dash, …) with a regular hyphen."""
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
    """Return the path to content.txt in the temp/ folder."""
    path = TEMP_DIR / CONTENT_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"ERROR: '{CONTENT_FILE}' not found in {TEMP_DIR}.\n"
            "Run extract_values.py first to generate it."
        )
    return path


# ── Reference word helpers ─────────────────────────────────────────────────────


def load_reference_words(path: Path | None = None) -> set[str]:
    """
    Build a set of normalised tokens from content.txt.

    Adds each full line and each whitespace-separated token individually.
    If path is None, loads from temp/content.txt.
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
    """Return normalised lines from content.txt in file order."""
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

    Each box is (x, y, w, h).
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
    """Return True if the given box overlaps any text box beyond the threshold."""
    for tb in text_boxes:
        if coverage((x, y, w, h), (tb["x"], tb["y"], tb["w"], tb["h"])) > threshold:
            return True
    return False


# ── CSV I/O ────────────────────────────────────────────────────────────────────


def read_csv_objects(csv_path: Path) -> list[dict]:
    """Read all rows from the objects CSV.

    Returns a list of dicts with keys: object_type, text, x, y, w, h.
    (w/h are used internally; the CSV stores them as width/height.)
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
                }
            )
    return objects


def write_csv_objects(objects: list[dict], csv_path: Path) -> None:
    """Write a list of object dicts (with w/h keys) to the CSV."""
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
                }
            )


def update_csv_objects(
    new_objects: list[dict], object_type: str, csv_path: Path
) -> None:
    """Replace all rows of the given object_type in the CSV with new_objects.

    Rows belonging to other object types are preserved.
    Creates the CSV (with headers) if it does not yet exist.
    """
    existing = read_csv_objects(csv_path) if csv_path.exists() else []
    kept = [o for o in existing if o["object_type"] != object_type]
    write_csv_objects(kept + new_objects, csv_path)
