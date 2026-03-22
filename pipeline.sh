#!/usr/bin/env bash
# pipeline.sh – Resume OCR pipeline runner
#
# Usage:
#   ./pipeline.sh [clean|text|objects|full]
#
# Modes:
#   clean   – Remove temp/ and output/ folders (cleanup from previous runs)
#   text    – OCR text extraction + annotation → annotated_text.png
#   objects – Text extraction + cleanup + object detection + annotation → annotated_objects.png
#   full    – Clean, text extraction + cleanup + object detection + annotation → annotated_full.png
#             (default when no argument is given)
#
# Pipeline sequence:
#   1. extract_values.py (generates temp/content.txt)
#   2. prepare_pipeline.py (initializes objects.csv)
#   3. text_extraction.py (OCR text detection)
#   4. text_cleanup.py (removes text regions when used in objects/full modes)
#   5. object_extraction.py (detects structural elements; uses text_cleaned.png if available)
#   6. order_objects.py (reorders objects.csv by content.txt order + structural)
#   7. image_annotation.py (draws bounding boxes on output image)
#
# Each Python script can also be run individually:
#   python extract_values.py
#   python ocr_pipeline/text_extraction.py
#   python ocr_pipeline/text_cleanup.py
#   python ocr_pipeline/object_extraction.py
#   python ocr_pipeline/image_annotation.py [--output FILENAME]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-full}"

# ── Locate Python ─────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found." >&2
    exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
run_step() {
    "$PYTHON" "$SCRIPT_DIR/ocr_pipeline/$1"
}

run_extract() {
    "$PYTHON" "$SCRIPT_DIR/extract_values.py"
}

run_annotate() {
    "$PYTHON" "$SCRIPT_DIR/ocr_pipeline/image_annotation.py" --output "$1"
}

run_cleanup() {
    "$PYTHON" "$SCRIPT_DIR/ocr_pipeline/text_cleanup.py"
}

run_order_objects() {
    "$PYTHON" "$SCRIPT_DIR/ocr_pipeline/order_objects.py"
}

clean_dirs() {
    echo "[clean] Removing temp/ and output/ folders …"
    rm -rf "$SCRIPT_DIR/temp" "$SCRIPT_DIR/output"
    mkdir -p "$SCRIPT_DIR/temp" "$SCRIPT_DIR/output"
    echo "[clean] Cleanup complete"
}

# ── Mode dispatch ─────────────────────────────────────────────────────────────
case "$MODE" in

    clean)
        echo "====== Mode: clean ======"
        clean_dirs
        ;;

    text)
        echo "====== Mode: text ======"
        run_extract
        run_step prepare_pipeline.py
        run_step text_extraction.py
        run_annotate annotated_text.png
        ;;

    objects)
        echo "====== Mode: objects ======"
        run_extract
        run_step prepare_pipeline.py
        run_step text_extraction.py
        run_cleanup
        run_step object_extraction.py
        run_order_objects
        run_annotate annotated_objects.png
        ;;

    full)
        echo "====== Mode: full ======"
        clean_dirs
        run_extract
        run_step prepare_pipeline.py
        run_step text_extraction.py
        run_cleanup
        run_step object_extraction.py
        run_order_objects
        run_annotate annotated_full.png
        ;;

    *)
        echo "Usage: $0 [clean|text|objects|full]"
        echo ""
        echo "  clean   – Remove temp/ and output/ folders (cleanup)"
        echo "  text    – OCR text extraction + annotation  (→ annotated_text.png)"
        echo "  objects – Structural detection + annotation (→ annotated_objects.png)"
        echo "  full    – Clean + text + structural + annotation (→ annotated_full.png)  [default]"
        exit 1
        ;;

esac

echo ""
echo "Done. Output saved to $SCRIPT_DIR/"
