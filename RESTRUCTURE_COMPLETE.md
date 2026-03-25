# Resume OCR Repository Restructure — Complete ✓

## Summary

The repository folder structure has been successfully reorganized from a scattered layout into a clean, pipeline-stage-based organization.

---

## New Structure

```
resume_ocr/
├── README.md
├── docs/                          # Documentation
│   ├── algorithm.md              # Pipeline overview & prerequisites
│   └── optimization.md           # CSS optimization strategy
│
├── source/                        # Human-maintained source of truth
│   ├── content.md                # Curated resume content
│   ├── template.html             # HTML template with rendering logic
│   ├── template.css              # Master stylesheet (modified by optimizer)
│   ├── fonts/                    # Font files referenced by CSS
│   └── references/               # Reference images (input scans)
│       └── Page_1.png           # Original resume scan
│
├── pipeline/                      # All 4 pipeline stages
│   ├── run.sh                    # Master orchestrator script
│   ├── extract/                  # Stage 1: Extract resume values
│   │   └── extract_values.py
│   ├── render/                   # Stage 2: Render HTML to PNG
│   │   └── render_html.py
│   ├── ocr/                      # Stage 3: OCR & detect elements
│   │   ├── prepare_pipeline.py
│   │   ├── text_extraction.py
│   │   ├── text_cleanup.py
│   │   ├── object_extraction.py
│   │   ├── order_objects.py
│   │   ├── image_annotation.py
│   │   └── utils.py             # Shared OCR configuration
│   └── optimize/                 # Stage 4: CSS optimization loop
│       ├── align_optimizer.py   # Main optimizer
│       ├── alignment_metric.py  # Scoring engine
│       ├── css_manager.py       # Safe CSS editor
│       └── tools/               # Manual inspection utilities
│           ├── analyze_gaps.py  # Debug misalignments
│           └── overlay_compare.py # Visual comparison
│
├── checkpoints/                   # CSS progress snapshots
│   ├── baseline.css              # After warm-start (~77%)
│   ├── warm_start.css            # Identical to baseline
│   └── drift_fix.css             # After drift correction (~85%)
│
└── generated/                     # Auto-generated artifacts (.gitignored)
    ├── .gitignore
    ├── resume.html               # Injected template (intermediate)
    ├── resume.css                # Adjusted stylesheet (intermediate)
    ├── Output_1.png              # Rendered resume screenshot
    ├── temp/
    │   ├── content.txt          # Extracted values (Stage 1 output)
    │   └── pipeline.log         # OCR pipeline logs
    └── ocr/
        ├── Output_1/
        │   └── objects.csv      # Rendered image OCR results
        └── Page_1/
            └── objects.csv      # Reference image OCR results
```

---

## Files Moved

| Old Location | New Location | Purpose |
|---|---|---|
| `html_info/` | `source/` | Source of truth (renamed for clarity) |
| `html_pipeline/extract_values.py` | `pipeline/extract/extract_values.py` | Stage 1 |
| `html_pipeline/render_html.py` | `pipeline/render/render_html.py` | Stage 2 |
| `ocr_pipeline/*` | `pipeline/ocr/*` | Stage 3 (entire folder) |
| `optimize_pipeline/align_optimizer.py` | `pipeline/optimize/align_optimizer.py` | Stage 4 |
| `optimize_pipeline/alignment_metric.py` | `pipeline/optimize/alignment_metric.py` | Scoring |
| `optimize_pipeline/css_manager.py` | `pipeline/optimize/css_manager.py` | CSS editor |
| `optimize_pipeline/analyze_gaps.py` | `pipeline/optimize/tools/analyze_gaps.py` | Tools |
| `optimize_pipeline/overlay_compare.py` | `pipeline/optimize/tools/overlay_compare.py` | Tools |
| `optimize_pipeline/progress/*.css` | `checkpoints/*.css` | CSS snapshots |
| `pipeline.sh` | `pipeline/run.sh` | Main orchestrator |
| `algorithm.md` | `docs/algorithm.md` | Documentation |
| `optimize_pipeline/optimization.md` | `docs/optimization.md` | Documentation |
| `image_reference/Output_1.png` | `generated/Output_1.png` | Rendered output |
| `image_reference/Page_1.png` | `source/references/Page_1.png` | Reference input |
| `temp/` | `generated/temp/` | Intermediates |
| `output/` | `generated/ocr/` | OCR results |
| `html_pipeline/resume.html` | `generated/resume.html` | Generated HTML |
| `html_pipeline/resume.css` | `generated/resume.css` | Generated CSS |

---

## Path Updates In Code

All Python scripts have been updated with correct path calculations:

### `pipeline/render/render_html.py`
- WORKSPACE: Now calculates 3 levels up (from `pipeline/render/`)
- Paths: `source/`, `generated/`

### `pipeline/ocr/utils.py`
- SCRIPT_DIR: Now calculates 3 levels up (from `pipeline/ocr/`)
- IMAGE_DIR: `source/references/`
- TEMP_DIR: `generated/temp/`
- Output dir: `generated/ocr/{image_stem}/`

### `pipeline/optimize/css_manager.py`
- WORKSPACE: Now calculates 3 levels up (from `pipeline/optimize/`)
- TEMPLATE_CSS: `source/template.css`

### `pipeline/optimize/align_optimizer.py`
- WORKSPACE: Now calculates 3 levels up
- Paths: `source/`, `generated/`
- Imports: Now local (from `alignment_metric` not `optimize_pipeline.alignment_metric`)
- Subprocess calls: Full paths to render and OCR scripts

### `pipeline/optimize/alignment_metric.py`
- WORKSPACE: Now calculates 3 levels up
- Image/CSV paths: Updated to `generated/ocr/` and `source/references/`

### `pipeline/run.sh`
- WORKSPACE: Now set as parent of SCRIPT_DIR
- Helper functions: Use `pipeline/extract/`, `pipeline/ocr/`
- Cleanup: Targets `generated/temp/` and `generated/ocr/`
- Collection: Looks in `source/references/`

---

## Benefits of New Structure

✅ **Clear pipeline organization** — Each stage has its own folder  
✅ **Separation of concerns** — Source, code, and artifacts are distinct  
✅ **Documentation co-located** — Docs folder at top level  
✅ **Generated artifacts isolated** — `.gitignore` in `generated/` prevents accidental commits  
✅ **Consistent naming** — All stages use `pipeline/` prefix  
✅ **Inspection tools separated** — `tools/` folder keeps utilities from core logic  

---

## Running the Pipeline

All commands work from the workspace root:

```bash
# Extract values and run OCR
python3 pipeline/extract/extract_values.py
pipeline/run.sh [clean|text|objects|full]

# Run optimizer
python3 pipeline/optimize/align_optimizer.py

# Inspect results
python3 pipeline/optimize/tools/analyze_gaps.py
python3 pipeline/optimize/tools/overlay_compare.py
```

---

## Notes

- Old empty folders remain at root level (`html_info/`, `html_pipeline/`, `ocr_pipeline/`, `optimize_pipeline/`, `temp/`, `output/`, `image_reference/`) but are unused. These can safely be deleted.
- All references to old paths in docstrings/help text are informational only; the functional code uses updated paths.
- The `.gitignore` in `generated/` ensures intermediate files don't get committed.
- CSS checkpoints in `checkpoints/` are historical snapshots and don't affect the pipeline.

