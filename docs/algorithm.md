# Resume OCR Alignment Pipeline

> **Purpose:** Align a CSS-rendered resume (`Output_1.png`) pixel-for-pixel with a
> reference scan (`Page_1.png`) by OCR-comparing the two images and
> iteratively tuning `source/template.css`.

---

## Prerequisites

You **must** have the following installed before running any step:

| Dependency | Install command | Why |
|---|---|---|
| Python 3.10+ | system/brew | all scripts |
| Tesseract OCR | `brew install tesseract` (macOS) | text extraction |
| Playwright + Chromium | `pip install playwright && playwright install chromium` | HTML→PNG render |
| Pillow | `pip install Pillow` | image I/O |
| scikit-image | `pip install scikit-image` | SSIM scoring |
| OpenCV | `pip install opencv-python` | image annotation |
| numpy | `pip install numpy` | array maths |

**Virtual environment (recommended):**
```bash
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt  # if present, else install packages above manually
```

> **ALL commands below must be run from the workspace root**
> (`/path/to/resume_ocr/`), not from inside a sub-folder.

---

## Source files — do NOT auto-generate these

These are human-curated inputs. Never overwrite them programmatically.

| File | Description |
|---|---|
| `source/template.css` | CSS stylesheet — the only file the optimizer edits |
| `source/template.html` | HTML skeleton for the resume |
| `source/content.md` | Resume content in `LABEL : value` format (see below) |
| `source/references/Page_1.png` | Ground-truth reference scan (never modified) |

### content.md format

Each non-blank line is one of:
- `LABEL : value` — a field; only the **value** (right side) is used
- `## SECTION : section_value` — section header; treated as a field
- `- LABEL : value` — list item field
- `### A : val_a | B : val_b | C : val_c` — multiple fields on one line (pipe-separated)

Lines starting with `#` (with no `:`) are ignored as pure comments.

---

## Step 1 — Extract content values

**Script:** `pipeline/extract/extract_values.py`  
**Run once** before the OCR pipeline, or whenever `content.md` changes.

```bash
python pipeline/extract/extract_values.py
```

**Reads:** `source/content.md`  
**Writes:** `generated/temp/content.txt` (one value per line, in document order)

`content.txt` is used by `pipeline/ocr/order_objects.py` to sort detected OCR
objects into the correct resume-field order.  If this file is missing or stale,
object ordering will be wrong and alignment scores will be low.

---

## Step 2 — Render HTML → PNG

**Script:** `pipeline/render/render_html.py`  
**Run every time** `template.css` or `content.md` changes.

```bash
python pipeline/render/render_html.py
```

**Reads:**
- `source/template.html`
- `source/content.md`
- `source/template.css`

**Writes:**
- `generated/resume.html` — injected HTML (intermediate; not the source)
- `generated/resume.css`  — copied CSS (intermediate; not the source)
- `generated/Output_1.png` — rendered screenshot (**this is the alignment target**)

Optional flags (all have defaults; only override if needed):
```bash
python pipeline/render/render_html.py \
    --template source/template.html \
    --md       source/content.md    \
    --html     generated/resume.html \
    --out      generated/Output_1.png \
    --width    1414 \
    --height   2000
```

**Failure modes:**
- `PlaywrightTimeoutError` → Chromium is not installed; run `playwright install chromium`.
- `FileNotFoundError` on template → confirm you are running from workspace root.

---

## Step 3 — OCR pipeline

**Script:** `./pipeline/run.sh`

Processes **every `*.png`** inside `source/references/` (both `Page_1.png` and
`Output_1.png`) and writes one `objects.csv` per image.

### Choosing the pipeline mode

| Command | What it does | When to use |
|---|---|---|
| `./pipeline/run.sh full` | Clean old output, then run full detection | Default; use this every time |
| `./pipeline/run.sh objects` | Full detection without pre-cleaning | Skip if `generated/` is already fresh |
| `./pipeline/run.sh text` | Text extraction + annotation only | Debugging text layer only |
| `./pipeline/run.sh clean` | Delete `generated/` only | Hard reset before a fresh run |

**Normal usage:**
```bash
chmod +x pipeline/run.sh   # only needed once
./pipeline/run.sh full
```

### What the pipeline does (per image, in order)

1. **`pipeline/ocr/prepare_pipeline.py`** — creates `generated/ocr/<ImageName>/objects.csv` with a header row.
2. **`pipeline/ocr/text_extraction.py`** — runs Tesseract; appends text bounding boxes to `objects.csv`.
3. **`pipeline/ocr/text_cleanup.py`** — blacks out text regions on a working copy of the image so structural detection ignores them (objects / full modes only).
4. **`pipeline/ocr/object_extraction.py`** — detects lines, rectangles, and other structural elements; appends to `objects.csv`.
5. **`pipeline/ocr/order_objects.py`** — sorts `objects.csv` rows to match the order in `generated/temp/content.txt`.
6. **`pipeline/ocr/image_annotation.py`** — draws coloured bounding boxes on a copy of the image; saves annotated PNG to `generated/ocr/<ImageName>/`.

**Outputs after a successful run:**
- `generated/ocr/Output_1/objects.csv` — detected objects in the rendered image
- `generated/ocr/Page_1/objects.csv`   — detected objects in the reference image
- `generated/temp/pipeline.log`        — timestamped log of every step

**Check the log for errors:**
```bash
cat generated/temp/pipeline.log
```

---

## Step 4 — Alignment optimisation

**Script:** `pipeline/optimize/align_optimizer.py`  
**Precondition:** Steps 1–3 must have completed successfully and both CSVs must exist.

```bash
python pipeline/optimize/align_optimizer.py           # full optimisation run
python pipeline/optimize/align_optimizer.py --dry-run # score current CSS only; no changes
```

### What the optimizer does

It compares `generated/ocr/Output_1/objects.csv` (rendered) against `generated/ocr/Page_1/objects.csv`
(reference) and edits `source/template.css` to reduce the pixel distance between
matched object pairs.

**Three automatic phases:**

| Phase | Name | Method | Expected score jump |
|---|---|---|---|
| 0 | Warm Start | 7 hard-coded analytical CSS changes | ~30 % → ~77 % |
| 1 | Drift Correction | 3 bullet/row-spacing fixes | ~77 % → ~85 % |
| 2 | Greedy Hill-Climbing | Try every CSS property × delta direction; keep best | ~85 % → ≥ 90 % |

**Each hill-climbing iteration:**
1. Snapshot current `template.css`.
2. Apply one CSS change (one property, one direction).
3. Re-render (`render_html.py`).
4. Re-run OCR pipeline (`pipeline.sh full`).
5. Score with `alignment_metric.py`.
6. **Keep** the change if `composite` improves by ≥ 1.5 %; otherwise **restore** snapshot.

### Understanding the composite score

`alignment_metric.py` returns:

| Key | Meaning | Target |
|---|---|---|
| `composite` | Primary score (0–100).  Weighted blend of alignment % + SSIM | ≥ 90.0 |
| `alignment_pct` | % of matched pairs where both Δx and Δy ≤ 20 px | ≥ 90 |
| `ssim` | Structural similarity index of the two full images (0–1) | ≥ 0.85 |
| `n_pairs` | Total matched object pairs | — |
| `n_aligned` | Pairs within the 20 px threshold | — |
| `mean_dy_main` | Signed mean vertical error for main-panel objects (px) | ~0 |
| `mean_dy_sidebar` | Signed mean vertical error for sidebar objects (px) | ~0 |
| `drift_slope` | Vertical drift added per px of y position | ~0 |

> A positive `mean_dy_*` means rendered objects are **below** the reference (increase top padding or decrease margins).  
> A negative `mean_dy_*` means rendered objects are **above** the reference (decrease top padding or increase margins).

### Supporting modules

| File | Role |
|---|---|
| `pipeline/optimize/alignment_metric.py` | CSV pair matching + SSIM composite score |
| `pipeline/optimize/css_manager.py` | Atomic read / patch / snapshot / restore of `template.css` |
| `pipeline/optimize/tools/analyze_gaps.py` | Per-pair gap diagnostic (prints which pairs are misaligned) |
| `pipeline/optimize/tools/overlay_compare.py` | Generates visual diff overlay images |
| `checkpoints/baseline.css` | CSS snapshot at start of optimisation |
| `checkpoints/warm_start.css` | CSS snapshot after Phase 0 |
| `checkpoints/drift_fix.css` | CSS snapshot after Phase 1 |
| `generated/optimize_logs.csv` | Per-iteration score history (append-only) |

### Outputs

| File | Description |
|---|---|
| `source/template.css` | Updated CSS (modified in-place) |
| `generated/optimize_logs.csv` | Score after every iteration |
| `generated/overlay_50.png` | Side-by-side overlay at 50 % opacity |
| `generated/overlay_diff.png` | Pixel-difference heatmap |
| `generated/overlay_side_by_side.png` | Reference vs rendered side by side |

---

## Step 5 — Repeat until aligned

After Step 4 completes, check the reported `composite` score:

```
composite ≥ 90.0  →  DONE.  Pipeline succeeded.
composite < 90.0  →  Repeat Steps 2–4.
```

**Repeat loop:**
```bash
python pipeline/render/render_html.py   # Step 2
./pipeline/run.sh full                  # Step 3
python pipeline/optimize/align_optimizer.py  # Step 4
# → check composite score printed at the end; repeat if < 90
```

Current best: **96.8 %** (90/93 pairs aligned).

---

## Full run — quick-start sequence

Run these commands in order from the workspace root to execute the entire pipeline
from scratch:

```bash
# 0. Activate virtual environment (if using one)
source .venv/bin/activate

# 1. Extract content values (once, or after editing content.md)
python pipeline/extract/extract_values.py

# 2. Render HTML → PNG
python pipeline/render/render_html.py

# 3. OCR pipeline (both images)
./pipeline/run.sh full

# 4. Optimise CSS alignment
python pipeline/optimize/align_optimizer.py

# 5. Check score — if composite < 90, repeat from step 2
python pipeline/optimize/align_optimizer.py --dry-run
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `playwright._impl._errors.Error: Executable doesn't exist` | Chromium not installed | `playwright install chromium` |
| `tesseract: command not found` | Tesseract not on PATH | `brew install tesseract` |
| `generated/ocr/Page_1/objects.csv` is empty | OCR found nothing | Check `generated/temp/pipeline.log`; ensure `source/references/Page_1.png` exists and is not blank |
| Composite score stuck below 77 % | Warm-start phase skipped or failed | Delete `checkpoints/warm_start.css` and re-run optimizer |
| `KeyError` in `alignment_metric.py` | `objects.csv` has wrong columns | Re-run `./pipeline/run.sh full` to regenerate CSVs |
| Score regresses between runs | `template.css` was not restored after a failed iteration | Copy `checkpoints/baseline.css` → `source/template.css` and restart |
| `FileNotFoundError: generated/temp/content.txt` | Step 1 was skipped | Run `python pipeline/extract/extract_values.py` first |