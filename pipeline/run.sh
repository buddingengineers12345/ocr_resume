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
# Multi-image support (Task 4):
#   All modes (except 'clean') iterate over every *.png in image_reference/.
#   The current image is passed to Python scripts via IMAGE_PATH env variable,
#   which is read by ocr_pipeline/utils.py:find_image().
#
# Pipeline sequence (per image):
#   1. html_pipeline/extract_values.py (generates temp/content.txt – runs once, not per image)
#   2. prepare_pipeline.py (initialises objects.csv for the image)
#   3. text_extraction.py (OCR text detection)
#   4. text_cleanup.py (removes text regions when used in objects/full modes)
#   5. object_extraction.py (detects structural elements)
#   6. order_objects.py (reorders objects.csv)
#   7. image_annotation.py (draws bounding boxes on output image)
#
# Logs:
#   All output is tee'd to temp/pipeline.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
MODE="${1:-full}"

# ── Logging ─────────────────────────────────────────────────────────────
mkdir -p "$WORKSPACE/generated/temp"
LOG_FILE="$WORKSPACE/generated/temp/pipeline.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Start fresh log for this run
echo "========================================" > "$LOG_FILE"
log "pipeline.sh  START  mode=$MODE"
echo "========================================" >> "$LOG_FILE"

# ── Locate Python ─────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    log "ERROR: Python not found."
    exit 1
fi
log "Python: $(command -v "$PYTHON")  ($("$PYTHON" --version 2>&1))"

# ── Helpers ───────────────────────────────────────────────────────────────────
run_step() {
    log "  -> $1"
    "$PYTHON" "$SCRIPT_DIR/ocr/$1" 2>&1 | tee -a "$LOG_FILE"
}

run_extract() {
    log "  -> extract/extract_values.py"
    "$PYTHON" "$SCRIPT_DIR/extract/extract_values.py" 2>&1 | tee -a "$LOG_FILE"
}

run_annotate() {
    log "  -> image_annotation.py --output $1"
    "$PYTHON" "$SCRIPT_DIR/ocr/image_annotation.py" --output "$1" 2>&1 | tee -a "$LOG_FILE"
}

run_cleanup() {
    log "  -> text_cleanup.py"
    "$PYTHON" "$SCRIPT_DIR/ocr/text_cleanup.py" 2>&1 | tee -a "$LOG_FILE"
}

run_order_objects() {
    log "  -> order_objects.py"
    "$PYTHON" "$SCRIPT_DIR/ocr/order_objects.py" 2>&1 | tee -a "$LOG_FILE"
}

clean_dirs() {
    log "[clean] Removing generated folder …"
    rm -rf "$WORKSPACE/generated/temp" "$WORKSPACE/generated/ocr"
    mkdir -p "$WORKSPACE/generated/temp" "$WORKSPACE/generated/ocr"
    # Re-open the log after cleaning temp/
    mkdir -p "$WORKSPACE/generated/temp"
    echo "========================================" > "$LOG_FILE"
    log "pipeline.sh  RESUMED AFTER CLEAN  mode=$MODE"
    echo "========================================" >> "$LOG_FILE"
    log "[clean] Cleanup complete"
}

# ── Collect images ────────────────────────────────────────────────────────────
# Returns a space-separated list of all *.png files in source/references/
# (sorted, .DS_Store and non-png files excluded automatically by glob)
collect_images() {
    local images=()
    for f in "$WORKSPACE/source/references/"*.png; do
        [[ -f "$f" ]] && images+=("$f")
    done
    echo "${images[@]}"
}

# ── Per-image pipeline helpers ────────────────────────────────────────────────
run_text_pipeline() {
    local img="$1" suffix="$2"
    local name
    name="$(basename "$img" .png)"
    log "--- Image: $name ---"
    export IMAGE_PATH="$img"
    run_step prepare_pipeline.py
    run_step text_extraction.py
    run_annotate "annotated_${suffix}_${name}.png"
    unset IMAGE_PATH
}

run_objects_pipeline() {
    local img="$1" suffix="$2"
    local name
    name="$(basename "$img" .png)"
    log "--- Image: $name ---"
    export IMAGE_PATH="$img"
    run_step prepare_pipeline.py
    run_step text_extraction.py
    run_cleanup
    run_step object_extraction.py
    run_order_objects
    run_annotate "annotated_${suffix}_${name}.png"
    unset IMAGE_PATH
}

# ── Mode dispatch ─────────────────────────────────────────────────────────────
case "$MODE" in

    clean)
        log "====== Mode: clean ======"
        clean_dirs
        ;;

    text)
        log "====== Mode: text ======"
        run_extract
        IMAGES=$(collect_images)
        if [[ -z "$IMAGES" ]]; then
            log "ERROR: No PNG images found in source/references/"
            exit 1
        fi
        COUNT=0
        for img in $IMAGES; do
            COUNT=$((COUNT + 1))
            log "Processing image $COUNT: $img"
            run_text_pipeline "$img" "text"
        done
        log "text mode complete – $COUNT image(s) processed"
        ;;

    objects)
        log "====== Mode: objects ======"
        run_extract
        IMAGES=$(collect_images)
        if [[ -z "$IMAGES" ]]; then
            log "ERROR: No PNG images found in source/references/"
            exit 1
        fi
        COUNT=0
        for img in $IMAGES; do
            COUNT=$((COUNT + 1))
            log "Processing image $COUNT: $img"
            run_objects_pipeline "$img" "objects"
        done
        log "objects mode complete – $COUNT image(s) processed"
        ;;

    full)
        log "====== Mode: full ======"
        clean_dirs
        run_extract
        IMAGES=$(collect_images)
        if [[ -z "$IMAGES" ]]; then
            log "ERROR: No PNG images found in source/references/"
            exit 1
        fi
        COUNT=0
        for img in $IMAGES; do
            COUNT=$((COUNT + 1))
            log "Processing image $COUNT: $img"
            run_objects_pipeline "$img" "full"
        done
        log "full mode complete – $COUNT image(s) processed"
        ;;

    *)
        log "Usage: $0 [clean|text|objects|full]"
        echo ""
        echo "  clean   – Remove temp/ and output/ folders (cleanup)"
        echo "  text    – OCR text extraction + annotation  (→ annotated_text_<image>.png)"
        echo "  objects – Structural detection + annotation (→ annotated_objects_<image>.png)"
        echo "  full    – Clean + text + structural + annotation (→ annotated_full_<image>.png) [default]"
        exit 1
        ;;

esac

log "========================================"
log "pipeline.sh  DONE"
log "========================================"
echo ""
echo "Done. Output saved to $WORKSPACE/generated/ocr/"
echo "Log written to $LOG_FILE"
