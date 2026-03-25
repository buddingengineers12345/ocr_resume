"""analyze_gaps — print a detailed alignment gap report.

Runs the alignment metric and tabulates matched pairs with their pixel
offsets, grouping misaligned and aligned pairs for inspection. Useful for
debugging specific alignment failures after a render/OCR run.
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
