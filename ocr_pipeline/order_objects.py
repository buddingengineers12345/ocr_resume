#!/usr/bin/env python3
"""
order_objects.py
================
Reorders objects.csv to match the reference order from content.txt.

Text objects are sorted according to their appearance in content.txt,
followed by all structural objects at the end.

Usage:
  python order_objects.py   # from workspace root
"""

from pathlib import Path
from ocr_pipeline.utils import (
    TEMP_DIR, OUTPUT_CSV, CONTENT_FILE,
    load_reference_order, read_csv_objects, write_csv_objects,
)


def order_objects():
    """
    Reorder objects.csv:
      1. Text objects in the order they appear in content.txt
      2. Structural objects at the end
    """
    csv_path = OUTPUT_CSV
    
    if not csv_path.exists():
        print(f"[order_objects] CSV not found: {csv_path}")
        return
    
    # Load reference order from content.txt
    content_path = TEMP_DIR / CONTENT_FILE
    reference_order = load_reference_order(content_path)
    print(f"[order_objects] Loaded {len(reference_order)} reference entries from content.txt")
    
    # Read all objects from CSV
    all_objects = read_csv_objects(csv_path)
    print(f"[order_objects] Loaded {len(all_objects)} objects from {csv_path.name}")
    
    # Separate text and structural objects
    text_objects = [o for o in all_objects if o["object_type"] in ("text", "char")]
    structural_objects = [o for o in all_objects if o["object_type"] == "structural"]
    
    print(f"[order_objects] Text objects: {len(text_objects)}, Structural: {len(structural_objects)}")
    
    # Build a mapping from text content to objects (handle duplicates)
    text_by_content = {}
    for obj in text_objects:
        content = obj["text"]
        if content not in text_by_content:
            text_by_content[content] = []
        text_by_content[content].append(obj)
    
    # Reorder: follow reference_order, pulling matching text objects
    ordered_text = []
    used_indices = {}  # Track which object instance we've used for each content
    
    for ref_text in reference_order:
        if ref_text in text_by_content:
            # Get the next unused object with this text
            idx = used_indices.get(ref_text, 0)
            candidates = text_by_content[ref_text]
            if idx < len(candidates):
                ordered_text.append(candidates[idx])
                used_indices[ref_text] = idx + 1
    
    # Add any text objects that weren't matched to reference_order
    for obj in text_objects:
        if obj not in ordered_text:
            ordered_text.append(obj)
    
    # Combine: ordered text + structural objects
    reordered = ordered_text + structural_objects
    
    # Write back to CSV
    write_csv_objects(reordered, csv_path)
    print(f"[order_objects] Reordered {len(reordered)} objects written to {csv_path.name}")
    print(f"  - Text objects (in content.txt order): {len(ordered_text)}")
    print(f"  - Structural objects: {len(structural_objects)}")


if __name__ == "__main__":
    order_objects()
