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

sys.path.insert(0, str(Path(__file__).parent))

from utils import OUTPUT_CSV, OUTPUT_DIR, find_image, update_csv_objects, GREEN, ensure_output_dir


def detect_text(image_path: Path) -> list:
    """
    Run Tesseract on the given image and return word-level detections as a list
    of dicts: {object_type, text, x, y, w, h}.
    Only entries with non-negative confidence are included.
    """
    import pytesseract
    from PIL import Image

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
    # custom_config = r'-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789•_ --psm 6'
    data    = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT, 
                                        # config=custom_config
                                        )

    objects = []
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        conf = int(data["conf"][i])
        if conf < 0 or not word:
            continue
        # Classify single characters as "char", multi-character words as "text"
        object_type = "char" if len(word) == 1 else "text"
        objects.append({
            "object_type": object_type,
            "text": word,
            "x":    data["left"][i],
            "y":    data["top"][i],
            "w":    data["width"][i],
            "h":    data["height"][i],
        })
    return objects


def run():
    import cv2
    
    image_path = find_image()
    ensure_output_dir()
    csv_path   = OUTPUT_CSV

    print("[text_extraction] Running OCR (word-level) …")
    text_objects = detect_text(image_path)
    print(f"[text_extraction] {len(text_objects)} word objects detected.")

    update_csv_objects(text_objects, "text", csv_path)
    print(f"[text_extraction] CSV updated → {csv_path.name}")
    
    # Visualize and save detected text boxes
    ensure_output_dir()
    image_bgr = cv2.imread(str(image_path))
    if image_bgr is not None:
        vis = image_bgr.copy()
        THICKNESS = 2
        FONT = cv2.FONT_HERSHEY_SIMPLEX
        FONT_SCALE = 0.35
        FONT_THICK = 1
        
        for obj in text_objects:
            x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
            cv2.rectangle(vis, (x, y), (x + w, y + h), GREEN, THICKNESS)
            cv2.putText(
                vis, obj["text"], (x, max(y - 3, 10)),
                FONT, FONT_SCALE, GREEN, FONT_THICK, cv2.LINE_AA,
            )
        
        out_path = OUTPUT_DIR / "text_detected.png"
        cv2.imwrite(str(out_path), vis)
        print(f"[text_extraction] Saved visualization → {out_path.name}")


if __name__ == "__main__":
    run()
