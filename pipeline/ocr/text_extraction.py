#!/usr/bin/env python3
"""text_extraction — multi-pass Tesseract OCR with preprocessing and merge.

Performs several preprocessing strategies (CLAHE, adaptive thresholding,
Otsu, sharpening) to recover words across varied background styles. Word
detections from all passes are merged using IoU/NMS heuristics to return a
clean set of word-level bounding boxes suitable for CSV output.

Usage:
        python pipeline/ocr/text_extraction.py
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    GREEN,
    get_output_csv,
    get_image_output_dir,
    ensure_output_dir,
    estimate_colors,
    find_image,
    load_reference_words,
    normalize_text,
    update_csv_objects,
)

# Scale factor for upscaling before OCR (Tesseract accuracy improves at higher res)
_OCR_SCALE = 2.0


# ---------------------------------------------------------------------------
# Preprocessing helpers
# ---------------------------------------------------------------------------

def _preprocess_clahe(bgr: np.ndarray, scale: float = _OCR_SCALE) -> Image.Image:
    """Upscale and apply CLAHE contrast enhancement on the L channel (LAB).

    Boosts local contrast in both dark and light regions, making faint text
    visible to Tesseract regardless of the underlying background colour.
    """
    h, w = bgr.shape[:2]
    if scale != 1.0:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    bgr_out = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    return Image.fromarray(cv2.cvtColor(bgr_out, cv2.COLOR_BGR2RGB))


def _preprocess_adaptive_binary(bgr: np.ndarray, scale: float = _OCR_SCALE,
                                  invert: bool = False) -> Image.Image:
    """Upscale, convert to grayscale, and apply adaptive Gaussian thresholding.

    Handles dark-on-dark and light-on-light text by using a local mean rather
    than a global threshold.  Pass *invert=True* to also cover light-on-dark
    regions (e.g. white text on a very dark sidebar).
    """
    h, w = bgr.shape[:2]
    if scale != 1.0:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    thresh_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresh_type,
        blockSize=25, C=10,
    )
    return Image.fromarray(binary)


def _preprocess_otsu(bgr: np.ndarray, scale: float = _OCR_SCALE,
                     invert: bool = False) -> Image.Image:
    """Upscale then apply Otsu global threshold on grayscale.

    Otsu picks the optimal global threshold automatically, which works well
    for images with bimodal intensity distributions (e.g. light text on a
    uniform dark sidebar).  Catches words that local-adaptive thresholding
    misses due to gradients or texture-based interference.
    """
    h, w = bgr.shape[:2]
    if scale != 1.0:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU if invert else cv2.THRESH_BINARY + cv2.THRESH_OTSU
    _, binary = cv2.threshold(gray, 0, 255, flag)
    return Image.fromarray(binary)


def _preprocess_sharpen_clahe(bgr: np.ndarray, scale: float = _OCR_SCALE) -> Image.Image:
    """Sharpen the image then apply CLAHE, combining edge accentuation with
    local contrast enhancement.

    The unsharp-mask sharpening step recovers slight blurring that can cause
    individual characters to bleed into neighbours, particularly in compressed
    or rendered-screenshot images where anti-aliasing softens strokes.
    """
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(bgr, -1, kernel)
    h, w = sharpened.shape[:2]
    if scale != 1.0:
        sharpened = cv2.resize(sharpened, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    bgr_out = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    return Image.fromarray(cv2.cvtColor(bgr_out, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------------------
# Tesseract wrapper
# ---------------------------------------------------------------------------

def _run_tesseract(pil_img: Image.Image, psm: int = 11) -> list[dict]:
    """Run Tesseract on a PIL image and return raw word-level detections.

    PSM 11 (sparse text) collects all text regardless of layout, which works
    well for multi-column resumes with mixed background regions.
    """
    config = f"--oem 3 --psm {psm}"
    data = pytesseract.image_to_data(pil_img, config=config,
                                     output_type=pytesseract.Output.DICT)
    results = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = int(data["conf"][i])
        if conf < 0 or not word:
            continue
        results.append({
            "text": word,
            "conf": conf,
            "x": data["left"][i],
            "y": data["top"][i],
            "w": data["width"][i],
            "h": data["height"][i],
        })
    return results


def _scale_coords(detections: list[dict], scale: float) -> list[dict]:
    """Divide bounding-box coordinates by *scale* (maps back to original image coords)."""
    for d in detections:
        d["x"] = int(round(d["x"] / scale))
        d["y"] = int(round(d["y"] / scale))
        d["w"] = max(1, int(round(d["w"] / scale)))
        d["h"] = max(1, int(round(d["h"] / scale)))
    return detections


# ---------------------------------------------------------------------------
# Multi-pass merge
# ---------------------------------------------------------------------------

def _iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two axis-aligned bounding boxes."""
    ix1 = max(a["x"], b["x"])
    iy1 = max(a["y"], b["y"])
    ix2 = min(a["x"] + a["w"], b["x"] + b["w"])
    iy2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _merge_passes(all_passes: list[list[dict]], iou_threshold: float = 0.35) -> list[dict]:
    """Merge detections from multiple preprocessing passes.

    Strategy: score each detection as ``confidence + 0.5 * min(len, 25)``, then
    greedily accept in descending score order.  The length bonus ensures that a
    complete word like ``Position_2_Project_2`` (len=21, conf=91, score≈101)
    beats a high-confidence partial like ``Project_2`` (len=9, conf=92, score≈96)
    that would otherwise block it via NMS.
    """
    flat = [d for pass_list in all_passes for d in pass_list]
    flat.sort(key=lambda d: d["conf"] + 0.5 * min(len(d["text"]), 25), reverse=True)
    kept: list[dict] = []
    for det in flat:
        if any(_iou(det, k) > iou_threshold for k in kept):
            continue
        kept.append(det)
    return kept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_text(image_path: Path) -> list[dict]:
    """Run multi-pass Tesseract OCR with preprocessing to handle varied image styles.

    Passes:
      1. CLAHE-enhanced colour image (2× upscale) – improves local contrast.
      2. Adaptive binary (dark text on light bg) – handles low-contrast dark panels.
      3. Adaptive binary inverted (light text on dark bg) – handles white-on-dark text.
      4. Otsu global threshold (normal + inverted) – bimodal images, sidebar awards.
      5. Sharpen + CLAHE – recovers softened/blurred strokes from anti-aliasing.

    Returns a list of dicts: {object_type, text, x, y, w, h}.
    Coordinates are in the original image's pixel space.
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

    bgr = cv2.imread(str(image_path))
    if bgr is None:
        # Fallback: let PIL/Tesseract open the file directly
        pil_img = Image.open(image_path)
        raw = _run_tesseract(pil_img, psm=11)
        objects = []
        for d in raw:
            text = d["text"]
            if not text or len(text) == 1:
                continue
            objects.append({"object_type": "text", "text": text,
                            "x": d["x"], "y": d["y"], "w": d["w"], "h": d["h"]})
        return objects

    all_passes: list[list[dict]] = []

    # Pass 1 – CLAHE contrast enhancement (handles both panels in colour space)
    pil_clahe = _preprocess_clahe(bgr, scale=_OCR_SCALE)
    pass1 = _run_tesseract(pil_clahe, psm=11)
    all_passes.append(_scale_coords(pass1, _OCR_SCALE))

    # Pass 2 – Adaptive binary: dark text on light background
    pil_bin = _preprocess_adaptive_binary(bgr, scale=_OCR_SCALE, invert=False)
    pass2 = _run_tesseract(pil_bin, psm=11)
    all_passes.append(_scale_coords(pass2, _OCR_SCALE))

    # Pass 3 – Adaptive binary inverted: light text on dark background
    pil_bin_inv = _preprocess_adaptive_binary(bgr, scale=_OCR_SCALE, invert=True)
    pass3 = _run_tesseract(pil_bin_inv, psm=11)
    all_passes.append(_scale_coords(pass3, _OCR_SCALE))

    # Pass 4 – Otsu global threshold: recovers words missed by local methods
    pil_otsu = _preprocess_otsu(bgr, scale=_OCR_SCALE, invert=False)
    pass4 = _run_tesseract(pil_otsu, psm=11)
    all_passes.append(_scale_coords(pass4, _OCR_SCALE))

    pil_otsu_inv = _preprocess_otsu(bgr, scale=_OCR_SCALE, invert=True)
    pass4b = _run_tesseract(pil_otsu_inv, psm=11)
    all_passes.append(_scale_coords(pass4b, _OCR_SCALE))

    # Pass 5 – Sharpen then CLAHE: recovers softened/blurred strokes
    pil_sharp = _preprocess_sharpen_clahe(bgr, scale=_OCR_SCALE)
    pass5 = _run_tesseract(pil_sharp, psm=11)
    all_passes.append(_scale_coords(pass5, _OCR_SCALE))

    merged = _merge_passes(all_passes)

    objects = []
    for d in merged:
        text = d["text"].strip()
        if not text or len(text) == 1:
            continue
        objects.append({
            "object_type": "text",
            "text": text,
            "x": d["x"],
            "y": d["y"],
            "w": d["w"],
            "h": d["h"],
        })
    return objects


def run() -> None:
    image_path = find_image()
    ensure_output_dir(image_path)
    output_csv = get_output_csv(image_path)
    output_dir = get_image_output_dir(image_path)

    print("[text_extraction] Running OCR (word-level) …")
    text_objects = detect_text(image_path)
    print(f"[text_extraction] {len(text_objects)} word objects detected.")

    image_bgr = cv2.imread(str(image_path))
    if image_bgr is not None:
        for obj in text_objects:
            color, bg_color = estimate_colors(image_bgr, obj["x"], obj["y"], obj["w"], obj["h"])
            obj["color"] = color
            obj["bg_color"] = bg_color
    else:
        for obj in text_objects:
            obj["color"] = ""
            obj["bg_color"] = ""

    # Tag objects not in content.txt that spatially overlap a content.txt object.
    ref_words = load_reference_words()
    matched = [o for o in text_objects if normalize_text(o["text"]) in ref_words]
    for obj in text_objects:
        if normalize_text(obj["text"]) not in ref_words:
            if any(_iou(obj, m) > 0.25 for m in matched):
                obj["object_type"] = "text_overlap"

    # Separate by type so update_csv_objects can clear each bucket cleanly.
    matched_objs = [o for o in text_objects if o["object_type"] == "text"]
    overlap_objs = [o for o in text_objects if o["object_type"] == "text_overlap"]

    # Clear stale rows for every type this step writes, then write fresh.
    for obj_type in ("char", "text", "text_overlap"):
        update_csv_objects([], obj_type, output_csv)
    # matched_objs: in content.txt → "text"
    # overlap_objs: not in content.txt but overlap a matched box → "text_overlap"
    update_csv_objects(matched_objs, "text", output_csv)
    update_csv_objects(overlap_objs, "text_overlap", output_csv)

    overlap_count = len(overlap_objs)
    print(f"[text_extraction] {overlap_count} text_overlap objects tagged.")
    print(f"[text_extraction] CSV updated → {output_csv.name}")

    if image_bgr is not None:
        vis = image_bgr.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        for obj in text_objects:
            x, y, w, h = obj["x"], obj["y"], obj["w"], obj["h"]
            cv2.rectangle(vis, (x, y), (x + w, y + h), GREEN, 2)
            cv2.putText(
                vis, obj["text"], (x, max(y - 3, 10)), font, 0.35, GREEN, 1, cv2.LINE_AA
            )

        out_path = output_dir / "text_detected.png"
        cv2.imwrite(str(out_path), vis)
        print(f"[text_extraction] Saved visualization → {out_path.name}")


if __name__ == "__main__":
    run()
