#!/usr/bin/env python3
"""text_extraction — multi-pass Tesseract OCR with preprocessing and merge.

**Purpose:**
Detects text regions in a resume image using Tesseract with multiple
preprocessing strategies to handle varied background styles and lighting.
Merges detections from all passes using IoU/NMS to produce a clean, de-duplicated
word-level bounding box dataset.

**Multi-pass strategy:**
Different preprocessing techniques extract text in different conditions:
- **CLAHE:** Local contrast enhancement (works on varied backgrounds)
- **Adaptive Binary:** Local thresholding (separates light/dark patterns)
- **Otsu:** Global thresholding (works on bimodal distributions)
- **Sharpen+CLAHE:** Edge enhancement + contrast (recovers blurred text)
- **Otsu Inverted:** For opposite foreground/background (white text on dark)

Each pass runs Tesseract (PSM 11 = sparse text mode) and detections are merged
using Intersection-over-Union (IoU) non-maximum suppression.

**Scoring & Merge:**
- Each detection scored as: confidence + 0.5 × min(text_length, 25)
- Length bonus helps long complete words beat high-confidence partials
- Greedy NMS keeps highest-scoring non-overlapping detections

**Output:**
- Writes detected text as rows in objects.csv (object_type="text")
- Each row: text, x, y, width, height, color (hex), bg_color (hex)
- Color estimation from surrounding pixels for visualization

**Input files:**
- source/references/Page_1.png (or IMAGE_PATH env var)
- generated/temp/content.txt (for reference word validation)

**Output files:**
- generated/ocr/{image_stem}/objects.csv (text objects appended)

**Usage:**
    python pipeline/ocr/text_extraction.py
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image

# Set pytesseract path explicitly to avoid hang on macOS
pytesseract.pytesseract.pytesseract_cmd = '/usr/local/bin/tesseract'

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    GREEN,
    get_output_csv,
    get_image_output_dir,
    ensure_output_dir,
    estimate_colors,
    find_image,
    load_reference_words,
    load_reference_order,
    get_content_path,
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

    **Technique:** Contrast-Limited Adaptive Histogram Equalization on L channel
    of LAB color space. Boosts local contrast in both dark and light regions,
    making faint text visible to Tesseract regardless of underlying background.
    
    Args:
        bgr: OpenCV BGR image (uint8)
        scale: Upscaling factor (Tesseract accuracy improves at 2x)
        
    Returns:
        PIL Image (RGB) with enhanced contrast
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

    **Technique:** Adaptive thresholding uses local mean rather than global
    threshold. Handles dark-on-dark and light-on-light text by adapting to
    regional intensity. Pass invert=True for light-on-dark (e.g., white text
    on dark sidebar).
    
    Args:
        bgr: OpenCV BGR image (uint8)
        scale: Upscaling factor
        invert: If True, use THRESH_BINARY_INV (useful for dark backgrounds)
        
    Returns:
        PIL Image (L mode, binary 0/255)
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

    **Technique:** Otsu automatically selects optimal global threshold by
    minimizing intra-class variance. Works well for bimodal intensity
    distributions (e.g., light text on uniform dark background). Catches
    words that local-adaptive thresholding misses due to gradients or texture.
    
    Args:
        bgr: OpenCV BGR image (uint8)
        scale: Upscaling factor
        invert: If True, use THRESH_BINARY_INV
        
    Returns:
        PIL Image (L mode, binary 0/255)
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

    **Technique:** Unsharp masking sharpens to recover blurring that causes
    character bleeding. Combined with CLAHE for robustness. Particularly
    effective on screenshots or rendered images with anti-aliasing artifacts.
    
    Args:
        bgr: OpenCV BGR image (uint8)
        scale: Upscaling factor
        
    Returns:
        PIL Image (RGB) with sharpening and contrast enhancement
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

    **Configuration:**
    - PSM 11: Sparse text mode (collects all text regardless of layout)
    - Works well for multi-column resumes with mixed backgrounds
    - Filters out zero-confidence or empty detections
    
    Args:
        pil_img: PIL Image to run OCR on
        psm: Page segmentation mode (default 11 = sparse text)
        
    Returns:
        list[dict]: Word detections with keys: text, conf, x, y, w, h
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
    """Divide bounding-box coordinates by *scale* (maps back to original image coords).
    
    Converts coordinates from upscaled space (used for OCR) back to original
    image coordinates. For example, with scale=2.0, a detection at (400, 400)
    maps back to (200, 200) in the original image.
    
    Args:
        detections: List of detection dicts with x, y, w, h keys
        scale: Scale factor used during preprocessing
        
    Returns:
        list[dict]: Modified detections with scaled-down coordinates
    """
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
    """Intersection-over-union of two axis-aligned bounding boxes.
    
    Computes (intersection_area / union_area) for determining if two
    detections overlap significantly. Used in NMS to filter duplicates.
    
    Args:
        a, b: Bounding boxes with keys x, y, w, h
        
    Returns:
        float: IoU in range [0.0, 1.0]
    """
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
    """Merge detections from multiple preprocessing passes using greedy NMS.

    **Scoring:**
    - Score = confidence + 0.5 × min(text_length, 25)
    - Length bonus helps long complete words beat high-confidence partials
    - Example: "Position_2_Project_2" (len=21, conf=91, score≈101) beats
      "Project_2" (len=9, conf=92, score≈96)
    
    **Greedy NMS:**
    - Sort all detections by descending score
    - Iterate in order, keeping detections that don't overlap (IoU < threshold)
    - with already-kept detections
    
    Args:
        all_passes: List of detection lists from all preprocessing passes
        iou_threshold: Minimum IoU to consider boxes as overlapping (default 0.35)
        
    Returns:
        list[dict]: Merged detections, deduplicated by IoU
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
    """Execute the text extraction OCR pipeline.
    
    **Steps:**
    1. Load input image and find/create output directory
    2. Run multi-pass Tesseract OCR to detect all text regions
    3. Estimate foreground/background colors for each detection
    4. Filter: keep only text matching content.txt reference
    5. Ensure all reference words appear in CSV (with empty coords if not detected)
    6. Write results to objects.csv, sorted by sequence
    
    **Input:** IMAGE_PATH env var or default image path
    **Output:** generated/ocr/{image_stem}/objects.csv
    """
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

    # Filter objects: only keep exact matches from content.txt
    # No spatial overlap objects — only exact matching text allowed.
    ref_words = load_reference_words()
    matched_objs = [o for o in text_objects if normalize_text(o["text"]) in ref_words]

    # Ensure all text from content.txt appears in CSV, with empty values for missing detections
    content_path = get_content_path()
    all_expected_text = load_reference_order(content_path)
    
    # Track which expected text entries were found
    detected_text_set = {normalize_text(obj["text"]) for obj in matched_objs}
    
    # Add missing text entries with empty values
    for expected_text in all_expected_text:
        if expected_text not in detected_text_set:
            matched_objs.append({
                "object_type": "text",
                "text": expected_text,
                "x": "",
                "y": "",
                "w": "",
                "h": "",
                "color": "",
                "bg_color": "",
            })

    # Clear stale rows for every type this step writes, then write fresh.
    for obj_type in ("char", "text", "text_overlap"):
        update_csv_objects([], obj_type, output_csv)
    # matched_objs: in content.txt → "text" (only exact matches kept, + unfound entries with empty values)
    update_csv_objects(matched_objs, "text", output_csv)

    filtered_count = len(text_objects) - len([o for o in text_objects if normalize_text(o["text"]) in ref_words])
    found_count = len(detected_text_set)
    missing_count = len(all_expected_text) - found_count
    print(f"[text_extraction] Found: {found_count}/{len(all_expected_text)} expected text entries, {missing_count} missing (empty rows added).")
    print(f"[text_extraction] Filtered {filtered_count} non-matching OCR objects.")
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
