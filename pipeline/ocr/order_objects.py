#!/usr/bin/env python3
"""order_objects — reorder OCR CSV rows to match content order.

Sorts text objects by their appearance in ``generated/temp/content.txt`` and
appends structural and character objects afterwards. Ensures CSV order
reflects the logical reading order for downstream processing.

Usage:
        python pipeline/ocr/order_objects.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    CONTENT_FILE,
    get_output_csv,
    TEMP_DIR,
    load_reference_order,
    read_csv_objects,
    write_csv_objects,
    find_image,
)


def order_objects() -> None:
    """Reorder objects.csv: text (by content.txt), structural (y desc), then char."""
    image_path = find_image()
    output_csv = get_output_csv(image_path)

    if not output_csv.exists():
        print(f"[order_objects] CSV not found: {output_csv}")
        return

    content_path = TEMP_DIR / CONTENT_FILE
    reference_order = load_reference_order(content_path)
    print(f"[order_objects] Loaded {len(reference_order)} entries from content.txt")

    all_objects = read_csv_objects(output_csv)
    print(f"[order_objects] Loaded {len(all_objects)} objects from {output_csv.name}")

    text_objects = [o for o in all_objects if o["object_type"] == "text"]
    char_objects = [o for o in all_objects if o["object_type"] == "char"]
    structural_objects = [o for o in all_objects if o["object_type"] == "structural"]
    print(
        f"[order_objects] Text: {len(text_objects)}, "
        f"Char: {len(char_objects)}, Structural: {len(structural_objects)}"
    )

    # Group text objects by content to handle duplicates gracefully
    text_by_content: dict[str, list[dict]] = {}
    for obj in text_objects:
        text_by_content.setdefault(obj["text"], []).append(obj)

    # Pull text objects in reference order, consuming one instance per occurrence
    used_indices: dict[str, int] = {}
    ordered_text: list[dict] = []
    for ref_text in reference_order:
        candidates = text_by_content.get(ref_text, [])
        idx = used_indices.get(ref_text, 0)
        if idx < len(candidates):
            ordered_text.append(candidates[idx])
            used_indices[ref_text] = idx + 1

    # Append any text objects not matched by the reference list
    matched_set = {id(obj) for obj in ordered_text}
    for obj in text_objects:
        if id(obj) not in matched_set:
            ordered_text.append(obj)

    # Structural objects sorted by y-coordinate descending (bottom of page first)
    ordered_structural = sorted(structural_objects, key=lambda o: o["y"], reverse=True)

    reordered = ordered_text + ordered_structural + char_objects
    write_csv_objects(reordered, output_csv)
    print(f"[order_objects] {len(reordered)} objects written to {output_csv.name}")
    print(f"  - Text objects (in content.txt order): {len(ordered_text)}")
    print(f"  - Structural objects (y descending)  : {len(ordered_structural)}")
    print(f"  - Char objects                       : {len(char_objects)}")


if __name__ == "__main__":
    order_objects()
