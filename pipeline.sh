#!/usr/bin/env bash
################################################################################
# Resume OCR Complete Pipeline
# 
# Orchestrates all 4 stages of the resume OCR pipeline:
#   1. Extract  – Extract fields from markdown content
#   2. Render   – Render HTML to PNG (1414x2000)
#   3. OCR      – Perform text/object extraction on rendered image
#   4. Optimize – Align rendered resume to reference via CSS tweaking
#   5. Compare  – Generate visual comparison artifacts against reference
#
# Usage:
#   ./pipeline.sh [extract|render|ocr|optimize|compare|full|dry-run]
#
# Modes:
#   extract      – Stage 1 only: extract resume fields from source/content.md
#   render       – Stage 2 only: render HTML template to PNG
#   ocr          – Stage 3 only: run OCR pipeline on source/references/ images
#   optimize     – Stage 4 only: align rendered resume to reference via CSS
#   compare      – Stage 5 only: generate side-by-side, overlay, diff heatmap
#   full         – All stages (1-5) sequentially
#   dry-run      – Print what would run without executing
#
# Requirements:
#   - Python 3.8+ with dependencies
#   - Tesseract OCR (stage 3)
#   - Playwright browser (stage 2 & 4)
#   - source/ folder with template.html, template.css, content.md
#   - source/references/ folder with reference PNG images
#
# Output:
#   generated/
#   ├── temp/                 # Temporary files and logs
#   ├── Output_1.png          # Rendered resume
#   ├── resume.html           # Built HTML
#   ├── resume.css            # Final CSS
#   ├── comparison/           # Visual comparison images
#   └── ocr/                  # OCR results per image
#       ├── Output_1/objects.csv
#       └── Page_1/objects.csv
#   checkpoints/              # CSS snapshots during optimization
#
# Exit codes:
#   0  – Success
#   1  – Stage failed
#   2  – Missing requirements
#   3  – Invalid mode/arguments
################################################################################

set -o pipefail
shopt -s nullglob  # Allow empty glob patterns

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}"
MODE="${1:-full}"
DRY_RUN=false

if [[ "$MODE" == "dry-run" ]]; then
    DRY_RUN=true
    MODE="${2:-full}"
fi

# ────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ────────────────────────────────────────────────────────────────────────────

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*"
}

log_step() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}▶ $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

log_error() {
    echo -e "${RED}✗ ERROR: $*${NC}" >&2
}

log_success() {
    echo -e "${GREEN}✓ $*${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $*${NC}"
}

run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY-RUN] Would execute: $*"
    else
        log "Executing: $*"
        if ! "$@"; then
            log_error "Command failed: $*"
            return 1
        fi
    fi
}

check_python() {
    if command -v python3 &>/dev/null; then
        PYTHON=python3
    elif command -v python &>/dev/null; then
        PYTHON=python
    else
        log_error "Python not found. Please install Python 3.8+"
        return 2
    fi
    log "Python: $PYTHON ($("$PYTHON" --version 2>&1))"
}

check_requirements() {
    local missing=0
    
    if [[ ! -f "$WORKSPACE/source/template.html" ]]; then
        log_error "Missing: source/template.html"
        missing=1
    fi
    
    if [[ ! -f "$WORKSPACE/source/template.css" ]]; then
        log_error "Missing: source/template.css"
        missing=1
    fi
    
    if [[ ! -f "$WORKSPACE/source/content.md" ]]; then
        log_error "Missing: source/content.md"
        missing=1
    fi
    
    if [[ ! -d "$WORKSPACE/source/references" ]]; then
        log_error "Missing: source/references/ folder"
        missing=1
    fi
    
    if [[ ! -d "$WORKSPACE/pipeline" ]]; then
        log_error "Missing: pipeline/ directory"
        missing=1
    fi
    
    return $missing
}

# ────────────────────────────────────────────────────────────────────────────
# STAGES
# ────────────────────────────────────────────────────────────────────────────

stage_extract() {
    log_step "STAGE 1: Extract Resume Fields"
    
    if [[ ! -f "$WORKSPACE/pipeline/extract/extract_values.py" ]]; then
        log_error "extract_values.py not found"
        return 1
    fi
    
    log "Extracting fields from source/content.md …"
    run_cmd "$PYTHON" "$WORKSPACE/pipeline/extract/extract_values.py" || return 1
    
    if [[ -f "$WORKSPACE/generated/temp/content.txt" ]]; then
        local count
        count=$(grep -c "=" "$WORKSPACE/generated/temp/content.txt" 2>/dev/null || echo 0)
        log_success "Extracted $count fields to generated/temp/content.txt"
    fi
}

stage_render() {
    log_step "STAGE 2: Render HTML to PNG"
    
    if [[ ! -f "$WORKSPACE/pipeline/render/render_html.py" ]]; then
        log_error "render_html.py not found"
        return 1
    fi
    
    log "Rendering template.html → Output_1.png (1414×2000 px) …"
    run_cmd "$PYTHON" "$WORKSPACE/pipeline/render/render_html.py" || return 1
    
    if [[ -f "$WORKSPACE/generated/Output_1.png" ]]; then
        local size
        size=$(stat -f%z "$WORKSPACE/generated/Output_1.png" 2>/dev/null || stat -c%s "$WORKSPACE/generated/Output_1.png" 2>/dev/null)
        log_success "Rendered image saved ($(printf '%.1f MB' $((size/1048576))))"
    fi
}

stage_ocr() {
    log_step "STAGE 3: OCR & Object Detection"
    
    if [[ ! -f "$WORKSPACE/pipeline/run.sh" ]]; then
        log_error "pipeline/run.sh not found"
        return 1
    fi
    
    local ocr_images
    ocr_images=("$WORKSPACE/source/references"/*.png)
    
    if [[ ${#ocr_images[@]} -eq 0 || "${ocr_images[0]}" == "$WORKSPACE/source/references/*.png" ]]; then
        log_error "No PNG files found in source/references/"
        return 1
    fi
    
    log "Processing ${#ocr_images[@]} reference image(s) …"
    run_cmd bash "$WORKSPACE/pipeline/run.sh" full || return 1
    
    # Also run OCR on the rendered Output_1.png for comparison
    if [[ -f "$WORKSPACE/generated/Output_1.png" ]]; then
        log "Processing rendered output (Output_1.png) …"
        export IMAGE_PATH="$WORKSPACE/generated/Output_1.png"
        mkdir -p "$WORKSPACE/generated/ocr/Output_1"
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/ocr/prepare_pipeline.py" || true
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/ocr/text_extraction.py" || true
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/ocr/text_cleanup.py" || true
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/ocr/object_extraction.py" || true
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/ocr/order_objects.py" || true
        unset IMAGE_PATH
    fi
    
    # Verify output
    if [[ -f "$WORKSPACE/generated/ocr/Output_1/objects.csv" ]] && \
       [[ -f "$WORKSPACE/generated/ocr/Page_1/objects.csv" ]]; then
        log_success "OCR complete: Output_1 and Page_1 CSV data generated"
    fi
}

stage_optimize() {
    log_step "STAGE 4: CSS Alignment Optimization"
    
    if [[ ! -f "$WORKSPACE/pipeline/optimize/align_optimizer.py" ]]; then
        log_error "align_optimizer.py not found"
        return 1
    fi
    
    # Check if any OCR CSV files were created (they may be in any subfolder of generated/ocr/)
    local ocr_csv_files
    ocr_csv_files=$(find "$WORKSPACE/generated/ocr" -name "objects.csv" -type f 2>/dev/null)
    if [[ -z "$ocr_csv_files" ]]; then
        log_error "OCR CSV files not found. Run stage 3 (ocr) first."
        return 1
    fi

    if [[ -f "$WORKSPACE/pipeline/optimize/visual_comparison.py" ]]; then
        log "Generating pre-optimization overlap preview …"
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/optimize/visual_comparison.py" || return 1
    fi
    
    log "Running alignment optimizer (max 5 hill-climb steps) …"
    run_cmd "$PYTHON" "$WORKSPACE/pipeline/optimize/align_optimizer.py" --max-steps 1 || return 1

    if [[ -f "$WORKSPACE/pipeline/optimize/visual_comparison.py" ]]; then
        log "Generating post-optimization overlap preview …"
        run_cmd "$PYTHON" "$WORKSPACE/pipeline/optimize/visual_comparison.py" || return 1
    fi
    
    # Check final alignment score
    if [[ -f "$WORKSPACE/generated/temp/pipeline.log" ]]; then
        local final_score
        final_score=$(sed -n 's/.*composite=[[:space:]]*\([0-9.][0-9.]*\)%.*/\1/p' "$WORKSPACE/generated/temp/pipeline.log" | tail -1)
        if [[ -n "$final_score" ]]; then
            log_success "Final alignment score: $final_score%"
        fi
    fi
}

stage_compare() {
    log_step "STAGE 5: Visual Comparison Artifacts"

    if [[ ! -f "$WORKSPACE/pipeline/optimize/visual_comparison.py" ]]; then
        log_error "visual_comparison.py not found"
        return 1
    fi

    if [[ ! -f "$WORKSPACE/generated/Output_1.png" ]]; then
        log_error "generated/Output_1.png not found. Run stage 2 (render) first."
        return 1
    fi

    if [[ ! -f "$WORKSPACE/source/references/Page_1.png" ]]; then
        log_error "source/references/Page_1.png not found"
        return 1
    fi

    log "Generating overlay, side-by-side, and heatmap comparison images …"
    run_cmd "$PYTHON" "$WORKSPACE/pipeline/optimize/visual_comparison.py" || return 1

    if [[ -f "$WORKSPACE/generated/comparison/overlay_comparison.png" ]] && \
       [[ -f "$WORKSPACE/generated/comparison/side_by_side_comparison.png" ]] && \
       [[ -f "$WORKSPACE/generated/comparison/diff_heatmap.png" ]]; then
        log_success "Visual comparison artifacts saved to generated/comparison/"
    fi
}

# ────────────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────────────

main() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Resume OCR Complete Pipeline              ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}\n"
    
    [[ "$DRY_RUN" == "true" ]] && log_warning "DRY-RUN MODE (no actual execution)\n"
    
    # Verify environment
    check_python || return 2
    check_requirements || return 2
    
    # Create required directories
    mkdir -p "$WORKSPACE/generated/temp"
    mkdir -p "$WORKSPACE/generated/ocr"
    mkdir -p "$WORKSPACE/checkpoints"
    
    local start_time
    start_time=$(date +%s)
    
    # Dispatch mode
    case "$MODE" in
        extract)
            stage_extract || return 1
            ;;
        render)
            stage_render || return 1
            ;;
        ocr)
            stage_ocr || return 1
            ;;
        optimize)
            stage_optimize || return 1
            stage_compare || return 1
            ;;
        compare)
            stage_compare || return 1
            ;;
        full)
            stage_extract || return 1
            stage_render || return 1
            stage_ocr || return 1
            stage_optimize || return 1
            stage_compare || return 1
            ;;
        *)
            log_error "Unknown mode: $MODE"
            echo ""
            echo "Usage: $0 [extract|render|ocr|optimize|compare|full|dry-run]"
            echo ""
            echo "Modes:"
            echo "  extract      – Stage 1: Extract fields from markdown"
            echo "  render       – Stage 2: Render HTML to PNG"
            echo "  ocr          – Stage 3: OCR and object detection"
            echo "  optimize     – Stage 4: CSS alignment optimization"
            echo "  compare      – Stage 5: Generate visual comparison images"
            echo "  full         – Run all stages sequentially (default)"
            echo "  dry-run      – Show what would run without executing"
            echo ""
            return 3
            ;;
    esac
    
    # Summary
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo -e "\n${BLUE}╔════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  ✓ Pipeline Complete                      ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}\n"
    
    log_success "Mode: $MODE"
    log_success "Duration: ${duration}s"
    log_success "Logs: $WORKSPACE/generated/temp/pipeline.log"
    echo ""
    
    return 0
}

main "$@"
exit $?
