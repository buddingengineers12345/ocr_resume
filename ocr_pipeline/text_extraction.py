#!/usr/bin/env python3
"""
text_extraction.py
==================
Step 2 of the OCR pipeline.

Runs Tesseract OCR on the input image in word-level mode, then writes
the detected text objects into objects.csv (replacing any previous text rows
while preserving structural rows from prior runs).

Usage:
  python ocr_pipeline/text_extraction.py   # from workspace root
  python text_extraction.py                # from inside ocr_pipeline/
"""

import sys
from pathlib import Path

import cv2
import pytesseract
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    GREEN,
    OUTPUT_CSV,
    OUTPUT_DIR,
    ensure_output_dir,
    find_image,
    update_csv_objects,
)


def detect_text(image_path: Path) -> list[dict]:
    """Run Tesseract on the given image and return word-level detections.

    Returns a list of dicts: {object_type, text, x, y, w, h}.
    Only entries with non-negative confidence are included.
    """
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        sys.exit(
            "\nERROR: Tesseract OCR binary not found.\n"
            "Install it with:\n"
            "  macOS : brew install tesseract\n"
            "  Ubuntu: sudo apt-get install tesseract-ocr\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
        )

    pil_img = Image.open(image_path)
    data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)

    objects = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = int(data["conf"][i])
        if conf < 0 or not word:
            continue
        object_type = "char" if len(word) == 1 else "text"
        objects.append(
            {
                "object_type": object_type,
                "text": word,
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
            }
        )
    return objects


def run() -> None:
    ensure_output_dir()

    image_path = find_image()

    print("[text_extraction] Running OCR (word-level) …")
    text_objects = detect_text(image_path)
    print(f"[text_extraction] {len(text_objects)} word objects detected.")

    update_csv_objects(text_objects, "text", OUTPUT_CSV)
    print(f"[text_extraction] CSV updated → {OUTPUT_CSV.name}")

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is not None:
        vis = image_bgr.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        for obj in text_objects:
            x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
            cv2.rectangle(vis, (x, y), (x + w, y + h), GREEN, 2)
            cv2.putText(
                vis, obj["text"], (x, max(y - 3, 10)), font, 0.35, GREEN, 1, cv2.LINE_AA
            )

        out_path = OUTPUT_DIR / "text_detected.png"
        cv2.imwrite(str(out_path), vis)
        print(f"[text_extraction] Saved visualization → {out_path.name}")


if __name__ == "__main__":
    run()
