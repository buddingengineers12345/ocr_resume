"""analyze_gaps — print a detailed alignment gap report.

**Purpose:**
Analyzes per-object alignment offsets after rendering and OCR. Displays
matched text pairs sorted by misalignment severity, useful for debugging
specific alignment problems and understanding where CSS adjustments are needed.

**Output:**
Tabular report showing:
- Text content (matched between Output_1 and Page_1)
- Bounding box coordinates (x, y) in both versions
- Per-axis offsets (dx = x_output - x_reference, dy likewise)
- Excess distance (Euclidean or custom metric)
- Grouped by aligned (< 20px) vs misaligned (> 20px)
- Sorted by severity (highest excess first)

**Typical workflow:**
1. Render resume and run OCR on Output_1.png
2. Run analyze_gaps.py to see which elements are misaligned
3. Identify patterns (e.g., all contact items shifted left by X pixels)
4. Adjust CSS properties accordingly
5. Re-render and repeat

**Inputs:**
- generated/ocr/Output_1/objects.csv
- generated/ocr/Page_1/objects.csv
- generated/Output_1.png
- source/references/Page_1.png

**Usage:**
    python pipeline/optimize/tools/analyze_gaps.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_ROOT))

from optimize_pipeline.alignment_metric import compute, print_report

CSV_O1 = _ROOT / "output" / "Output_1" / "objects.csv"
CSV_P1 = _ROOT / "output" / "Page_1"   / "objects.csv"
IMG_O1 = _ROOT / "image_reference" / "Output_1.png"
IMG_P1 = _ROOT / "image_reference" / "Page_1.png"


def _tabulate(pairs: list[dict], title: str) -> None:
    """Print a formatted table of alignment pairs.
    
    Args:
        pairs: List of pair dicts with alignment offset info
        title: Section header (e.g., "MISALIGNED PAIRS")
    """
    print(f"\n=== {title} ===")
    hdr = f"{'text':45s}  {'x_o1':>6} {'x_p1':>6} {'y_o1':>6} {'y_p1':>6} {'dx':>6} {'dy':>6} {'excess':>7}"
    print(hdr)
    for p in pairs:
        print(
            f"{str(p['text'])[:45]:45s}  "
            f"{p['o1_x']:6.0f} {p['p1_x']:6.0f} "
            f"{p['o1_y']:6.0f} {p['p1_y']:6.0f} "
            f"{p['dx']:+6.0f} {p['dy']:+6.0f} "
            f"{p['excess']:7.1f}"
        )


def main() -> None:
    """Compute metrics, tabulate misaligned then aligned pairs, print report.
    
    **Execution:**
    1. Compute all alignment metrics between Output_1 and Page_1
    2. Sort pairs: misaligned (excess > threshold) then aligned
    3. Print each group in tabular format with coordinates and offsets
    4. Print summary metrics report
    """
    m = compute(CSV_O1, CSV_P1, IMG_O1, IMG_P1)

    misaligned = sorted(
        [p for p in m["pairs_df"] if not p["aligned"]],
        key=lambda x: x["excess"],
        reverse=True,
    )
    aligned = sorted(
        [p for p in m["pairs_df"] if p["aligned"]],
        key=lambda x: x["excess"],
    )

    _tabulate(misaligned, "MISALIGNED PAIRS")
    _tabulate(aligned, "ALIGNED PAIRS")

    print()
    print_report(m)


if __name__ == "__main__":
    main()
