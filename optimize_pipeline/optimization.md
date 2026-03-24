# Resume Layout Alignment Optimizer — Plan & Analysis

## Goal
Align the rendered HTML resume (`image_reference/Output_1.png`) to the reference image
(`image_reference/Page_1.png`) by modifying only `html_info/template.css`, iterating
until **≥ 90% of matched text-object pairs are within ±20 px in both x and y**.

---

## Quantitative Pre-Analysis

### Matched pair count
~61 exact-text-field matches between `output/Output_1/objects.csv` and
`output/Page_1/objects.csv` (type=`text` only; `text_overlap` / `structural` excluded).

### Per-region error summary (before any optimization)

| Region | Mean Δy | Mean Δx | Pairs | Aligned@20px |
|--------|---------|---------|-------|--------------|
| Main — section headers | +13 px | +8 px | 8 | 7/8 |
| Main — bullet items | **+26 px** (growing) | 0 px | 36 | 14/36 |
| Sidebar — contact/awards | −33 px | **−78 px** | 13 | 0/13 |
| Company / dates | +22 px | **+60 px** | 6 | 0/6 |
| **Total** | | | **61** | **~25%** |

### Drift slope
Bullet Δy grows at **+0.014 px per pixel** down the page. Over the full page
(y: 500 → 1880) it accumulates **+43 px** of drift above the initial offset.
Root cause: per-bullet spacing in the rendered HTML is 34.4 px, reference is 31.6 px.

---

## Root Cause Mapping

| # | Symptom | Root CSS property | Current | Target | Δ |
|---|---------|-------------------|---------|--------|---|
| 1 | NAME 19 px too low | `#main padding-top` | 59 px | 40 px | −19 px |
| 2 | Contact pill 32 px too high | `.photo-wrap padding-bottom` | 58 px | 90 px | +32 px |
| 3 | Contact text 78 px too far left | `#sb-contact padding-left` | 46 px | 126 px | +80 px |
| 4 | Award text 62 px too far left | `#sb-awards padding-left` | 49 px | 111 px | +62 px |
| 5 | Bullet spacing 2.8 px excess | `.proj-list li margin-bottom` | 4 px | 1 px | −3 px |
| 6 | Contact rows Y off ~27 px | `.crow margin-bottom` | 26 px | 21 px | −5 px |
| 7 | Award rows Y off ~25 px | `.arow margin-bottom` | 23 px | 19 px | −4 px |

Fixes 1-4 are analytically derived (exact pixel measurements).  
Fix 5 resolves the growing drift slope.  
Fixes 6-7 fine-tune sidebar Y positions.

---

## Metrics

### Stop condition (binary)
```
alignment_pct = n_pairs_with(|Δy| ≤ 20 AND |Δx| ≤ 20) / n_total × 100
STOP when alignment_pct ≥ 90.0
```

### Continuous objective (for hill-climbing)
```
mean_excess = mean(max(0, |Δy|−20) + max(0, |Δx|−20)  for all pairs)
```
Lower is better. Minimising `mean_excess` drives `alignment_pct` up smoothly.

### Signed directional metrics (halve search space)
```
mean_Δy_main     = mean(Δy for pairs with OCR x > 540)   — was +26 px
mean_Δy_sidebar  = mean(Δy for pairs with OCR x < 540)   — was −31 px
mean_Δx_contact  = mean(Δx for contact/award pairs)      — was −78 px
drift_slope      = linregress(y, Δy) slope for bullet pairs
```

### Secondary (image-level sanity)
```
ssim = structural_similarity(Output_1.png, Page_1.png, multichannel)
composite = 0.70 × alignment_pct + 0.30 × ssim × 100
```

---

## Three-Phase Optimization

### Phase 0 — Analytical Warm Start (1 render)
Apply 4 derived CSS changes at once. Expected: **~77 % alignment**.

### Phase 1 — Drift Correction (1–3 renders)
Apply bullet spacing and sidebar row-margin fixes. Expected: **~85 % alignment**.

### Phase 2 — Hill-Climbing (≤ 40 renders)
Direction-aware greedy search over the remaining candidate properties.
Uses signed metrics to pick delta direction; accepts improvement only if
`composite` rises by ≥ 1.5 % (noise guard).

---

## CSS Tweak Catalogue

| Name | Selector | Property | Deltas |
|------|----------|----------|--------|
| main_pad_top | `#main` | padding-top | −1…−10 |
| main_pad_left | `#main` | padding-left | −1…−10 |
| photo_bot_pad | `.photo-wrap` | padding-bottom | ±2…±12 |
| sb_contact_pl | `#sb-contact` | padding-left | −5…+20 |
| sb_contact_pr | `#sb-contact` | padding-right | −5…+10 |
| sb_awards_pl | `#sb-awards` | padding-left | −5…+20 |
| crow_mb | `.crow` | margin-bottom | ±1…±6 |
| arow_mb | `.arow` | margin-bottom | ±1…±6 |
| pill_mb | `.pill` | margin-bottom | ±2…±8 |
| pill_width | `.pill` | width | ±4…±20 |
| name_mb | `#r-name` | margin-bottom | ±2…±10 |
| profile_mb | `#profile` | margin-bottom | ±2…±10 |
| sec_head_mb | `.sec-head` | margin-bottom | ±2…±10 |
| job_mb | `.job` | margin-bottom | ±2…±10 |
| proj_mb | `.proj` | margin-bottom | ±2…±8 |
| proj_name_mb | `.proj-name` | margin-bottom | ±1…±6 |
| bullet_li_mb | `.proj-list li` | margin-bottom | ±1…±3 |
| bullet_lh | `.proj-list li` | line-height | ±0.05…±0.20 |
| job_company_ls | `.job-company` | letter-spacing | ±0.5…±2 |
| job_dates_size | `.job-dates` | font-size | ±1…±4 |

---

## Pipeline per Iteration

```
1. css_manager.apply_patch(selector, prop, new_val)
2. python html_pipeline/render_html.py          → updates Output_1.png
3. IMAGE_PATH=.../Output_1.png ./pipeline steps → updates output/Output_1/objects.csv
4. alignment_metric.compute() → composite score
5. If improved: keep; else: css_manager.restore(snapshot)
```

Page_1.png / Page_1/objects.csv are **never re-processed** during the loop.

---

## Files

| File | Purpose |
|------|---------|
| `optimize_pipeline/alignment_metric.py` | Load CSVs, match pairs, compute all metrics |
| `optimize_pipeline/css_manager.py` | Read / patch / restore template.css safely |
| `optimize_pipeline/align_optimizer.py` | Main loop: warm start → drift fix → hill-climb |
| `optimize_pipeline/optimization.md` | This document |
| `optimize_pipeline/progress/` | CSS + overlap snapshots per iteration |
| `optimize_pipeline/iteration_log.csv` | Per-iteration score history |

---

## Expected output
```
[WARM START] composite=77.4%  (align=74.4%, ssim=81.0%)
[DRIFT FIX]  composite=83.1%  (align=80.3%, ssim=85.0%)
[ITER  1]    composite=86.0%  ...
[ITER  7]    composite=91.2%  ← STOP (≥ 90%)
CSS written to html_info/template.css
```
