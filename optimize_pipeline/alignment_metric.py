"""
alignment_metric.py
-------------------
Measures how well the rendered resume (Output_1) is aligned with the
reference page (Page_1) using:

  1. CSV position alignment  – per-pair pixel error on matched text objects
  2. SSIM image similarity   – structural similarity on the full images

Exports
-------
compute(csv_o1, csv_p1, img_o1, img_p1) -> dict
    Keys:
        composite       float   0-100  (primary optimisation target)
        alignment_pct   float   0-100  (% pairs within ±20 px)
        ssim            float   0-1    (structural similarity)
        mean_excess     float   px     (mean clamped-to-zero error per pair)
        n_pairs         int
        n_aligned       int
        mean_dy_main    float   (signed mean Δy for main-panel objects)
        mean_dy_sidebar float   (signed mean Δy for sidebar objects)
        mean_dx_contact float   (signed mean Δx for sidebar contact/award)
        drift_slope     float   (px of Δy added per px of y – bullet drift)
        pairs_df        list[dict]   per-pair details for logging
"""

import csv
import difflib
import os
from pathlib import Path

import numpy as np

# ── Optional scikit-image ─────────────────────────────────────────────────────
try:
    from skimage.metrics import structural_similarity as _ssim_fn
    _HAVE_SKIMAGE = True
except ImportError:
    _HAVE_SKIMAGE = False

# ── Optional PIL ──────────────────────────────────────────────────────────────
try:
    from PIL import Image as _PIL_Image
    _HAVE_PIL = True
except ImportError:
    _HAVE_PIL = False

# ── Paths (workspace root = parent of this script's directory) ─────────────────
WORKSPACE = Path(__file__).parent.parent.resolve()
CSV_O1    = WORKSPACE / "output" / "Output_1" / "objects.csv"
CSV_P1    = WORKSPACE / "output" / "Page_1"   / "objects.csv"
IMG_O1    = WORKSPACE / "image_reference" / "Output_1.png"
IMG_P1    = WORKSPACE / "image_reference" / "Page_1.png"

ALIGN_THRESHOLD   = 20   # px – both Δx and Δy must be within this
SIDEBAR_SPLIT_X   = 540  # px – objects left of this are "sidebar"
FUZZY_RATIO       = 0.85  # minimum SequenceMatcher ratio for fuzzy match
MIN_COMPOSITE_IMPROVE = 1.5  # % – minimum gain to accept a hill-climb step


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_csv(path: Path) -> list[dict]:
    """Read objects.csv, coerce numeric columns, return list of dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            row["x"]      = int(row["x"])
            row["y"]      = int(row["y"])
            row["width"]  = int(row["width"])
            row["height"] = int(row["height"])
            rows.append(row)
    return rows


def _text_objects(rows: list[dict]) -> list[dict]:
    """Filter to exact 'text' object_type only (exclude text_overlap, structural, char).
    Also exclude very short OCR fragments (< 4 chars) that cause bad cross-matches."""
    return [r for r in rows if r["object_type"] == "text" and len(r["text"].strip()) >= 4]


# ── Text matching ─────────────────────────────────────────────────────────────

def _normalize(t: str) -> str:
    """Lowercase, strip, collapse whitespace, normalise dashes."""
    return t.lower().strip().replace("—", "-").replace("–", "-")


def _fuzzy_match(a: str, b: str) -> bool:
    an, bn = _normalize(a), _normalize(b)
    if an == bn:
        return True
    ratio = difflib.SequenceMatcher(None, an, bn).ratio()
    return ratio >= FUZZY_RATIO


def _build_pairs(objs_o1: list[dict], objs_p1: list[dict]) -> list[dict]:
    """
    Match O1 text objects to P1 text objects by text field.
    Exact matches preferred; fuzzy fallback for dash-normalisation etc.
    Returns list of {o1: row, p1: row, dx: int, dy: int, text: str}.
    """
    # Build lookup: text → list of rows (for duplicates)
    p1_by_text: dict[str, list[dict]] = {}
    for r in objs_p1:
        p1_by_text.setdefault(_normalize(r["text"]), []).append(r)

    used_p1: set[int] = set()  # ids of matched P1 rows
    pairs = []

    for o1r in objs_o1:
        key = _normalize(o1r["text"])
        candidates = p1_by_text.get(key, [])

        # Pick the closest unmatched candidate by existing y-distance
        best = None
        best_dist = float("inf")
        for p1r in candidates:
            rid = id(p1r)
            if rid in used_p1:
                continue
            dist = abs(o1r["y"] - p1r["y"])
            if dist < best_dist:
                best_dist = dist
                best = p1r

        if best is None:
            # Try fuzzy match
            for norm_key, p1_list in p1_by_text.items():
                if not _fuzzy_match(o1r["text"], norm_key):
                    continue
                for p1r in p1_list:
                    rid = id(p1r)
                    if rid in used_p1:
                        continue
                    dist = abs(o1r["y"] - p1r["y"])
                    if dist < best_dist:
                        best_dist = dist
                        best = p1r

        if best is None:
            continue  # unmatched

        used_p1.add(id(best))
        pairs.append({
            "text": o1r["text"],
            "o1_x": o1r["x"],  "o1_y": o1r["y"],
            "p1_x": best["x"], "p1_y": best["y"],
            "dx": o1r["x"] - best["x"],
            "dy": o1r["y"] - best["y"],
        })

    return pairs


# ── SSIM ──────────────────────────────────────────────────────────────────────

def _compute_ssim(img_o1: Path, img_p1: Path) -> float:
    if not (_HAVE_SKIMAGE and _HAVE_PIL):
        return 0.75  # neutral fallback when deps unavailable

    try:
        SIZE = (1414, 2000)
        o1 = np.array(
            _PIL_Image.open(img_o1).convert("RGB").resize(SIZE, _PIL_Image.LANCZOS),
            dtype=np.float64,
        )
        p1 = np.array(
            _PIL_Image.open(img_p1).convert("RGB").resize(SIZE, _PIL_Image.LANCZOS),
            dtype=np.float64,
        )
        # Mask the top toolbar strip (first ~42 px) which differs by design
        o1[:42] = p1[:42]
        s = _ssim_fn(o1, p1, channel_axis=2, data_range=255.0)
        return float(np.clip(s, 0.0, 1.0))
    except Exception:
        return 0.75


# ── Directional metrics ───────────────────────────────────────────────────────

def _directional_metrics(pairs: list[dict]) -> dict:
    """Compute signed mean deltas and bullet drift slope."""
    main_dy, sidebar_dy, contact_dx = [], [], []
    bullet_y, bullet_dy = [], []

    for p in pairs:
        is_sidebar = p["o1_x"] < SIDEBAR_SPLIT_X
        if is_sidebar:
            sidebar_dy.append(p["dy"])
            contact_dx.append(p["dx"])
        else:
            main_dy.append(p["dy"])

        # Bullet items have leading "Position_" and "_Info_" in text
        txt = p["text"]
        if "_Project_" in txt and "_Info_" in txt:
            bullet_y.append(p["o1_y"])
            bullet_dy.append(p["dy"])

    # Drift slope via linear regression (Δy vs y for bullets)
    drift_slope = 0.0
    if len(bullet_y) >= 3:
        y_arr  = np.array(bullet_y,  dtype=float)
        dy_arr = np.array(bullet_dy, dtype=float)
        y_c  = y_arr  - y_arr.mean()
        dy_c = dy_arr - dy_arr.mean()
        denom = (y_c * y_c).sum()
        if denom > 0:
            drift_slope = float((y_c * dy_c).sum() / denom)

    def _mean(lst):
        return float(np.mean(lst)) if lst else 0.0

    return {
        "mean_dy_main":    _mean(main_dy),
        "mean_dy_sidebar": _mean(sidebar_dy),
        "mean_dx_contact": _mean(contact_dx),
        "drift_slope":     drift_slope,
    }


# ── Core compute ──────────────────────────────────────────────────────────────

def compute(
    csv_o1: Path = CSV_O1,
    csv_p1: Path = CSV_P1,
    img_o1: Path = IMG_O1,
    img_p1: Path = IMG_P1,
) -> dict:
    """
    Main entry point.  Reads CSVs and images from disk every call
    (so re-running after each optimizer render picks up fresh data).
    """
    rows_o1 = _load_csv(csv_o1)
    rows_p1 = _load_csv(csv_p1)

    objs_o1 = _text_objects(rows_o1)
    objs_p1 = _text_objects(rows_p1)

    pairs = _build_pairs(objs_o1, objs_p1)
    n_pairs = len(pairs)

    if n_pairs == 0:
        return {
            "composite": 0.0, "alignment_pct": 0.0, "ssim": 0.0,
            "mean_excess": 9999.0, "n_pairs": 0, "n_aligned": 0,
            "mean_dy_main": 0.0, "mean_dy_sidebar": 0.0,
            "mean_dx_contact": 0.0, "drift_slope": 0.0, "pairs_df": [],
        }

    # Per-pair alignment and excess error
    n_aligned = 0
    excess_list = []
    for p in pairs:
        ax = abs(p["dx"])
        ay = abs(p["dy"])
        aligned = ax <= ALIGN_THRESHOLD and ay <= ALIGN_THRESHOLD
        if aligned:
            n_aligned += 1
        excess = max(0, ay - ALIGN_THRESHOLD) + max(0, ax - ALIGN_THRESHOLD)
        excess_list.append(excess)
        p["aligned"] = aligned
        p["excess"]  = excess

    alignment_pct = n_aligned / n_pairs * 100.0
    mean_excess   = float(np.mean(excess_list))

    ssim_val = _compute_ssim(img_o1, img_p1)

    composite = 0.70 * alignment_pct + 0.30 * ssim_val * 100.0

    dir_metrics = _directional_metrics(pairs)

    return {
        "composite":       round(composite,     2),
        "alignment_pct":   round(alignment_pct, 2),
        "ssim":            round(ssim_val,       4),
        "mean_excess":     round(mean_excess,    2),
        "n_pairs":         n_pairs,
        "n_aligned":       n_aligned,
        "mean_dy_main":    round(dir_metrics["mean_dy_main"],    2),
        "mean_dy_sidebar": round(dir_metrics["mean_dy_sidebar"], 2),
        "mean_dx_contact": round(dir_metrics["mean_dx_contact"], 2),
        "drift_slope":     round(dir_metrics["drift_slope"],     5),
        "pairs_df":        pairs,
    }


# ── CLI helper ────────────────────────────────────────────────────────────────

def print_report(m: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  Alignment   : {m['alignment_pct']:6.1f}%  ({m['n_aligned']}/{m['n_pairs']} pairs ≤ 20 px)")
    print(f"  SSIM        : {m['ssim']:6.4f}")
    print(f"  Composite   : {m['composite']:6.1f}%")
    print(f"  Mean excess : {m['mean_excess']:6.1f} px")
    print(f"  Δy main     : {m['mean_dy_main']:+.1f} px")
    print(f"  Δy sidebar  : {m['mean_dy_sidebar']:+.1f} px")
    print(f"  Δx contact  : {m['mean_dx_contact']:+.1f} px")
    print(f"  Drift slope : {m['drift_slope']:+.5f}")
    print(f"{'='*60}\n")
    # Worst 10 pairs
    worst = sorted(m["pairs_df"], key=lambda x: x["excess"], reverse=True)[:10]
    if worst:
        print("  Worst pairs:")
        for p in worst:
            flag = "✓" if p["aligned"] else "✗"
            print(f"    {flag} {p['text']:<45}  Δy={p['dy']:+4d}  Δx={p['dx']:+4d}  excess={p['excess']:.0f}")
    print()


if __name__ == "__main__":
    m = compute()
    print_report(m)
