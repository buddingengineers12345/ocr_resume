"""
align_optimizer.py
------------------
Main optimization loop.  Modifies html_info/template.css to align the
rendered resume with the reference image to ≥ 90 % alignment.

Three phases
------------
Phase 0 — Analytical Warm Start
    Apply 7 analytically-derived CSS changes (exact pixel measurements).
    Expected jump: ~25 % → ~77 % alignment in one render.

Phase 1 — Drift Correction
    Apply 3 bullet/row-spacing fixes that resolve growing y-drift.
    Expected jump: ~77 % → ~85 % alignment.

Phase 2 — Greedy Hill-Climbing
    Direction-aware property search.  Each iteration tries every property
    in the catalogue × every candidate delta, keeps the best improvement.
    Accepts only if composite score rises by ≥ MIN_IMPROVE %.

Usage
-----
    python optimize_pipeline/align_optimizer.py          # from workspace root
    python optimize_pipeline/align_optimizer.py --dry-run  # score only, no changes
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Workspace root ─────────────────────────────────────────────────────────────
WORKSPACE = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(WORKSPACE / "pipeline" / "optimize"))

from alignment_metric import (
    compute as metric_compute,
    print_report,
    MIN_COMPOSITE_IMPROVE,
)
from css_manager import CSSManager

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_ALIGNMENT   = 90.0        # % – stop condition
MAX_ITER_HILLCLIMB = 50          # safety cap on hill-climbing iterations
GENERATED_DIR      = WORKSPACE / "generated"
PROGRESS_DIR       = GENERATED_DIR / "temp"
LOG_CSV            = GENERATED_DIR / "optimize_logs.csv"

CSS_PATH           = WORKSPACE / "source" / "template.css"
IMG_O1             = GENERATED_DIR / "Output_1.png"
IMG_P1             = WORKSPACE / "source" / "references" / "Page_1.png"
CSV_O1             = GENERATED_DIR / "ocr" / "Output_1" / "objects.csv"
CSV_P1             = GENERATED_DIR / "ocr" / "Page_1" / "objects.csv"

PYTHON = sys.executable

# ── Render + OCR ──────────────────────────────────────────────────────────────

def _run(cmd: list, env: dict | None = None, label: str = "") -> int:
    """Run a subprocess, stream stdout/stderr, return exit code."""
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        cwd=str(WORKSPACE),
        env=full_env,
    )
    return result.returncode


def render_output() -> None:
    """Re-render resume.html → Output_1.png via Playwright (with 1 retry)."""
    for attempt in range(2):
        rc = _run([PYTHON, str(WORKSPACE / "pipeline" / "render" / "render_html.py")], label="render")
        if rc == 0:
            return
        if attempt == 0:
            print(f"  [WARN] render_html.py failed (exit {rc}), retrying in 3s…")
            time.sleep(3)
    raise RuntimeError(f"render_html.py failed after 2 attempts")


def run_ocr_output_only() -> None:
    """
    Run the OCR pipeline steps for Output_1.png only
    (skipping Page_1.png to avoid expensive re-OCR of the reference).
    """
    img_path = str(IMG_O1)
    env = {"IMAGE_PATH": img_path}

    steps = [
        str(WORKSPACE / "pipeline" / "ocr" / "prepare_pipeline.py"),
        str(WORKSPACE / "pipeline" / "ocr" / "text_extraction.py"),
        str(WORKSPACE / "pipeline" / "ocr" / "text_cleanup.py"),
        str(WORKSPACE / "pipeline" / "ocr" / "object_extraction.py"),
        str(WORKSPACE / "pipeline" / "ocr" / "order_objects.py"),
    ]
    for step in steps:
        rc = _run([PYTHON, step], env=env, label=step)
        if rc != 0:
            print(f"  [WARN] {step} exited with code {rc} – continuing")


def render_and_score(label: str = "") -> dict:
    """Render, run OCR, return metric dict."""
    render_output()
    run_ocr_output_only()
    m = metric_compute(csv_o1=CSV_O1, csv_p1=CSV_P1, img_o1=IMG_O1, img_p1=IMG_P1)
    return m


# ── Logging ───────────────────────────────────────────────────────────────────

_LOG_FIELDNAMES = [
    "phase", "iteration", "composite", "alignment_pct", "ssim",
    "mean_excess", "n_aligned", "n_pairs",
    "mean_dy_main", "mean_dy_sidebar", "mean_dx_contact", "drift_slope",
    "applied_selector", "applied_prop", "applied_delta",
]

def _init_log() -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=_LOG_FIELDNAMES).writeheader()


def _append_log() -> None:
    """Ensure the log file exists with a header (for resume mode)."""
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_CSV.exists():
        _init_log()


def _log_row(phase: str, iteration: int, m: dict,
             selector: str = "", prop: str = "", delta=None) -> None:
    row = {
        "phase":              phase,
        "iteration":          iteration,
        "composite":          m["composite"],
        "alignment_pct":      m["alignment_pct"],
        "ssim":               m["ssim"],
        "mean_excess":        m["mean_excess"],
        "n_aligned":          m["n_aligned"],
        "n_pairs":            m["n_pairs"],
        "mean_dy_main":       m["mean_dy_main"],
        "mean_dy_sidebar":    m["mean_dy_sidebar"],
        "mean_dx_contact":    m["mean_dx_contact"],
        "drift_slope":        m["drift_slope"],
        "applied_selector":   selector,
        "applied_prop":       prop,
        "applied_delta":      "" if delta is None else delta,
    }
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=_LOG_FIELDNAMES).writerow(row)


def _print_iter(phase: str, it: int, m: dict, applied: str = "") -> None:
    tag = f"[{phase} {it:02d}]" if it >= 0 else f"[{phase}]"
    app = f"  applied: {applied}" if applied else ""
    print(
        f"{tag}  composite={m['composite']:5.1f}%"
        f"  align={m['alignment_pct']:5.1f}%"
        f"  ssim={m['ssim']:.4f}"
        f"  excess={m['mean_excess']:5.1f} px"
        f"{app}"
    )


def _save_css_snapshot(tag: str) -> None:
    snap = CSS_PATH.read_text(encoding="utf-8")
    out  = PROGRESS_DIR / f"{tag}.css"
    out.write_text(snap, encoding="utf-8")


# ── Phase 0 – Analytical Warm Start ──────────────────────────────────────────

# Properties derived from exact pixel measurements on the current CSV diff.
# These are applied as a batch then rendered once.
WARM_START_PATCHES = [
    # (selector,         prop,              target_value)
    # Main panel: NAME is 19 px too low → reduce padding-top 59→40
    # Current shorthand: padding: 59px 63px 72px 66px  → top=59 → 40
    ("#main",           "padding-top",       40),
    # Sidebar: contact pill 32 px too HIGH → increase photo-wrap padding-bottom 58→90
    # Current shorthand: padding: 44px 0 58px  → bottom=58 → 90
    (".photo-wrap",     "padding-bottom",    90),
    # Sidebar: contact text 78 px too far LEFT → expand to 4-value, left=126
    # Current shorthand: padding: 0 46px  (= 0 46 0 46)  → left=46 → 126
    ("#sb-contact",     "padding-left",      126),
    # Also reduce right to avoid clipping
    ("#sb-contact",     "padding-right",     30),
    # Sidebar: award text 62 px too far LEFT → padding-left 49→111
    ("#sb-awards",      "padding-left",      111),
    ("#sb-awards",      "padding-right",     30),
]

def phase0_warm_start(mgr: CSSManager, dry_run: bool = False) -> dict:
    print("\n" + "="*60)
    print("PHASE 0 — Analytical Warm Start")
    print("="*60)

    mgr.snapshot()

    if not dry_run:
        # Apply each patch with the most appropriate method
        n_ok = 0
        for selector, prop, value in WARM_START_PATCHES:
            if prop in ("padding-top", "padding-bottom", "padding-left", "padding-right"):
                side = prop.replace("padding-", "")
                result = mgr.set_padding_side(selector, side, value)
            else:
                result = mgr.set_value(selector, prop, value)
            if result:
                n_ok += 1
                print(f"  ✓ {selector} :: {prop} = {value}")
            else:
                print(f"  ✗ FAILED: {selector} :: {prop} = {value}")
        print(f"  Applied {n_ok}/{len(WARM_START_PATCHES)} patches")
        m = render_and_score()
    else:
        m = metric_compute(csv_o1=CSV_O1, csv_p1=CSV_P1, img_o1=IMG_O1, img_p1=IMG_P1)

    _print_iter("WARM", -1, m)
    _log_row("warm_start", 0, m, "batch", "batch", "batch")
    _save_css_snapshot("warm_start")
    return m


# ── Phase 1 – Drift Correction ────────────────────────────────────────────────

DRIFT_PATCHES = [
    # Bullet spacing: 34.4 px actual vs 31.6 px reference → -3px margin-bottom
    (".proj-list li",   "margin-bottom",     1),
    # Contact row Y: still ~27 px off → tighten crow margin-bottom 26→21
    (".crow",           "margin-bottom",     21),
    # Award row Y: still ~25 px off → tighten arow margin-bottom 23→19
    (".arow",           "margin-bottom",     19),
]

def phase1_drift_correction(mgr: CSSManager, baseline: dict,
                             dry_run: bool = False) -> dict:
    print("\n" + "="*60)
    print("PHASE 1 — Drift Correction")
    print("="*60)

    best = dict(baseline)

    for selector, prop, target in DRIFT_PATCHES:
        if best["alignment_pct"] >= TARGET_ALIGNMENT:
            print(f"  → Target reached early, skipping remaining drift patches")
            break

        curr = mgr.get_numeric(selector, prop)
        if curr is None:
            curr = mgr.get_padding_side(selector, prop.replace("padding-", ""))
        print(f"  Patching {selector} :: {prop}: {curr} → {target}")

        snap = mgr.snapshot()
        if not dry_run:
            mgr.set_value(selector, prop, target)
            m = render_and_score()
        else:
            m = dict(best)

        if m["composite"] >= best["composite"] - 0.5:
            best = m
            _print_iter("DRIFT", -1, m, f"{selector} :: {prop} = {target}")
            _log_row("drift", 0, m, selector, prop, target)
        else:
            print(f"  [revert] {selector} :: {prop} = {target} degraded composite")
            mgr.restore(snap)

    _save_css_snapshot("drift_fix")
    return best


# ── Phase 2 – Greedy Hill-Climbing ────────────────────────────────────────────

# Catalogue: (selector, prop, [delta_candidates])
# Delta candidates are signed increments, not absolute values.
# Direction-aware filtering reduces them each iteration based on directional metrics.
TWEAK_CATALOGUE = [
    # ── Main panel Y ──────────────────────────────────────────────────────────
    ("#main",            "padding-top",      [-3, -2, -1, 1, 2, 3, 5, 8, 10]),
    ("#main",            "padding-left",     [-4, -2, -1, 1, 2, 4, 6, 8]),
    # padding-right controls right-aligned elements (company, dates) position
    # Company names are ~68px too far right → increase padding-right by ~68
    ("#main",            "padding-right",    [-4, -2, 5, 10, 15, 20, 30, 40, 50, 68]),
    ("#r-name",          "margin-bottom",    [-4, -2, -1, 1, 2, 4, 6]),
    ("#profile",         "margin-bottom",    [-4, -2, 2, 4, 6, 8]),
    (".sec-head",        "margin-bottom",    [-4, -2, 2, 4, 6]),
    (".job",             "margin-bottom",    [-4, -2, -1, 1, 2, 4, 6]),
    (".proj",            "margin-bottom",    [-4, -2, -1, 1, 2, 4]),
    (".proj-name",       "margin-bottom",    [-4, -2, -1, 1, 2, 4, 6]),
    (".proj-list li",    "margin-bottom",    [-1, 1, 2]),
    (".proj-list li",    "line-height",      [-0.1, -0.05, 0.05, 0.1, 0.15]),
    # ── Sidebar Y ────────────────────────────────────────────────────────────
    (".photo-wrap",      "padding-bottom",   [-4, -2, 2, 4, 6, 8]),
    (".photo-wrap",      "padding-top",      [-4, -2, 2, 4]),
    (".pill",            "margin-bottom",    [-4, -2, 2, 4, 6]),
    (".crow",            "margin-bottom",    [-4, -2, -1, 1, 2, 4]),
    (".arow",            "margin-bottom",    [-4, -2, -1, 1, 2, 4]),
    ("#sb-contact",      "margin-bottom",    [-6, -4, -2, 2, 4, 6, 8, 10]),
    # ── Sidebar X (contact/award icon indent) ───────────────────────────────
    ("#sb-contact",      "padding-left",     [-10, -5, -4, -2, 2, 4, 5, 10]),
    ("#sb-awards",       "padding-left",     [-10, -5, -4, -2, 2, 4, 5, 10]),
    (".adot",            "margin-right",     [-4, -2, 2, 4]),
    (".cicon",           "margin-right",     [-2, 2, 4]),
    # ── Company / dates X ────────────────────────────────────────────────────
    (".job-company",     "letter-spacing",   [-1, -0.5, 0.5, 1]),
    (".job-company",     "margin-right",     [-4, -2, 2, 4, 8]),
    (".job-dates",       "font-size",        [-1, 1, 2, 3]),
    (".job-pos",         "font-size",        [-2, -1, 1, 2]),
    (".job-hrow",        "margin-bottom",    [-2, -1, 1, 2, 4]),
    # ── General fine-tune ────────────────────────────────────────────────────
    (".pill",            "width",            [-8, -4, 4, 8, 12]),
    (".pline",           "line-height",      [-0.1, -0.05, 0.05, 0.1]),
    # ── Position 3 bug fix (bullets ~22px too high in Y) ─────────────────────
    (".job",             "margin-bottom",    [-4, -2, 2, 4, 6, 8, 10]),
]


def _direction_filter(deltas: list, m: dict, selector: str, prop: str) -> list:
    """
    Remove deltas that push in the wrong direction based on signed metrics.
    Keeps all deltas when direction is ambiguous (|signal| < 3 px).
    """
    md_y = m.get("mean_dy_main", 0)
    sb_y = m.get("mean_dy_sidebar", 0)
    sb_x = m.get("mean_dx_contact", 0)
    drift = m.get("drift_slope", 0)

    # Map property → which metric it primarily affects
    # Positive delta → y increases (items move down), x increases (items move right)
    prop_region = {
        "padding-top": "main_y",   "padding-bottom": "sb_y",  "padding-left": "main_x",
        "margin-bottom": None,      "line-height": "drift",    "letter-spacing": "company_x",
        "margin-right": None,       "font-size": None,         "width": None,
    }.get(prop)

    if prop_region == "main_y":
        # main items are too LOW (md_y > 0) → decrease padding-top → negative delta preferred
        if md_y > 3:  return [d for d in deltas if d < 0] or deltas
        if md_y < -3: return [d for d in deltas if d > 0] or deltas
    elif prop_region == "sb_y":
        # sidebar items are too HIGH (sb_y < 0) → increase padding-bottom → positive delta
        if sb_y < -3: return [d for d in deltas if d > 0] or deltas
        if sb_y > 3:  return [d for d in deltas if d < 0] or deltas
    elif prop_region == "drift":
        # drift_slope > 0 → bullet spacing too large → decrease line-height
        if drift > 0.005: return [d for d in deltas if d < 0] or deltas

    return deltas


def phase2_hill_climb(mgr: CSSManager, baseline: dict,
                      dry_run: bool = False) -> dict:
    print("\n" + "="*60)
    print("PHASE 2 — Greedy Hill-Climbing")
    print("="*60)

    best = dict(baseline)
    no_improve_streak = 0
    MAX_NO_IMPROVE = 5

    for iteration in range(1, MAX_ITER_HILLCLIMB + 1):
        if best["alignment_pct"] >= TARGET_ALIGNMENT:
            print(f"\n  ★ TARGET {TARGET_ALIGNMENT}% REACHED at iteration {iteration-1}")
            break

        print(f"\n  --- Iter {iteration} | composite={best['composite']:.1f}% "
              f"align={best['alignment_pct']:.1f}% ---")

        best_delta_composite = best["composite"]
        best_delta_m         = None
        best_delta_selector  = None
        best_delta_prop      = None
        best_delta_delta     = None

        for selector, prop, raw_deltas in TWEAK_CATALOGUE:
            deltas = _direction_filter(raw_deltas, best, selector, prop)

            # Get current value — handle padding shorthands
            if prop.startswith("padding-"):
                side = prop.replace("padding-", "")
                curr = mgr.get_padding_side(selector, side)
            elif prop == "padding":
                curr = mgr.get_padding_side(selector, "top")  # use top as proxy
            else:
                curr = mgr.get_numeric(selector, prop)

            if curr is None:
                continue

            for delta in deltas:
                new_val = round(curr + delta, 3)
                if new_val < 0:
                    continue  # don't allow negative lengths

                snap = mgr.snapshot()
                if not dry_run:
                    if prop.startswith("padding-"):
                        side = prop.replace("padding-", "")
                        mgr.set_padding_side(selector, side, new_val)
                    else:
                        mgr.set_value(selector, prop, new_val)
                    m = render_and_score()
                else:
                    m = dict(best)
                    m["composite"] -= 0.1  # simulate no gain in dry-run

                if m["composite"] > best_delta_composite:
                    best_delta_composite = m["composite"]
                    best_delta_m         = m
                    best_delta_selector  = selector
                    best_delta_prop      = prop
                    best_delta_delta     = delta

                # Always revert after sampling
                mgr.restore(snap)

        # Apply the best delta found in this iteration
        if (best_delta_m is not None and
                best_delta_composite - best["composite"] >= MIN_COMPOSITE_IMPROVE):

            # Apply the winning tweak cleanly
            if best_delta_prop.startswith("padding-"):
                side_key = best_delta_prop.replace("padding-", "")
                curr_val = mgr.get_padding_side(best_delta_selector, side_key) or 0
                mgr.set_padding_side(best_delta_selector, side_key,
                                     round(curr_val + best_delta_delta, 3))
            else:
                curr_val = mgr.get_numeric(best_delta_selector, best_delta_prop) or 0
                mgr.set_value(best_delta_selector, best_delta_prop,
                              round(curr_val + best_delta_delta, 3))
            # Re-render with the accepted change applied cleanly
            if not dry_run:
                best = render_and_score()
            else:
                best = best_delta_m

            applied = (f"{best_delta_selector} :: {best_delta_prop} "
                       f"Δ={best_delta_delta:+.2f}")
            _print_iter("HILL", iteration, best, applied)
            _log_row("hill", iteration, best,
                     best_delta_selector, best_delta_prop, best_delta_delta)
            _save_css_snapshot(f"iter_{iteration:03d}")
            no_improve_streak = 0

        else:
            print(f"  No improvement ≥ {MIN_COMPOSITE_IMPROVE}% found — streak {no_improve_streak+1}/{MAX_NO_IMPROVE}")
            no_improve_streak += 1
            if no_improve_streak >= MAX_NO_IMPROVE:
                print("  → Plateau reached, stopping hill-climb")
                break

    return best


# ── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False, resume: bool = False) -> None:
    t0 = time.time()
    mgr = CSSManager(CSS_PATH)
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)

    if resume:
        # ── Resume mode: skip phases 0 and 1, score current CSS state ─────────
        print("\n" + "="*60)
        print("RESUME MODE — skipping warm-start and drift phases")
        print("="*60)
        _append_log()  # keep existing log, don't wipe it
        m = metric_compute(csv_o1=CSV_O1, csv_p1=CSV_P1,
                           img_o1=IMG_O1, img_p1=IMG_P1)
        _print_iter("RESUME", -1, m)
        print_report(m)
        if m["alignment_pct"] >= TARGET_ALIGNMENT:
            print(f"\n  ✓ Already at {m['alignment_pct']:.1f}% — nothing to do.")
            return
        m = phase2_hill_climb(mgr, m, dry_run=dry_run)
        _print_final(m, t0)
        return

    _init_log()

    # ── Baseline score ────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("BASELINE — initial score (no changes)")
    print("="*60)
    baseline = metric_compute(csv_o1=CSV_O1, csv_p1=CSV_P1,
                              img_o1=IMG_O1, img_p1=IMG_P1)
    _print_iter("BASE", -1, baseline)
    print_report(baseline)
    _log_row("baseline", 0, baseline)

    if baseline["alignment_pct"] >= TARGET_ALIGNMENT:
        print(f"\n  ✓ Already at {baseline['alignment_pct']:.1f}% — nothing to do.")
        return

    # Record a full CSS snapshot before we touch anything
    mgr.snapshot()
    _save_css_snapshot("baseline")

    # ── Phase 0 ───────────────────────────────────────────────────────────────
    m = phase0_warm_start(mgr, dry_run=dry_run)
    if m["alignment_pct"] >= TARGET_ALIGNMENT:
        _print_final(m, t0)
        return

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    m = phase1_drift_correction(mgr, m, dry_run=dry_run)
    if m["alignment_pct"] >= TARGET_ALIGNMENT:
        _print_final(m, t0)
        return

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    m = phase2_hill_climb(mgr, m, dry_run=dry_run)

    _print_final(m, t0)


def _print_final(m: dict, t0: float) -> None:
    elapsed = time.time() - t0
    print("\n" + "="*60)
    print("FINAL RESULT")
    print("="*60)
    print_report(m)
    status = "✓ TARGET MET" if m["alignment_pct"] >= TARGET_ALIGNMENT else "✗ TARGET NOT MET"
    print(f"  {status}  alignment={m['alignment_pct']:.1f}%  composite={m['composite']:.1f}%")
    print(f"  Time elapsed: {elapsed:.0f}s")
    print(f"  CSS: {CSS_PATH}")
    print(f"  Log: {LOG_CSV}")
    print(f"  Snapshots: {PROGRESS_DIR}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resume layout alignment optimizer")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Score only; do not modify CSS or re-render",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip phases 0 and 1; hill-climb from current CSS state",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, resume=args.resume)
