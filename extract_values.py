#!/usr/bin/env python3
"""
extract_values.py
=================
Parses content.md and writes all label values to temp/content.txt.

Handles piped formats and ignores section headers (# lines) and list
markers (- lines).

Usage:
  python extract_values.py   # from workspace root
"""

from collections import Counter
from pathlib import Path


def extract_values_from_md() -> None:
    """Read content.md, extract colon-separated values, write to temp/content.txt."""
    workspace_root = Path(__file__).parent.resolve()
    content_md_path = workspace_root / "content.md"
    temp_dir = workspace_root / "temp"
    content_txt_path = temp_dir / "content.txt"

    temp_dir.mkdir(parents=True, exist_ok=True)

    values: list[str] = []
    with open(content_md_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            elif line.startswith("-"):
                line = line[1:].strip()

            if "|" in line:
                for part in line.split("|"):
                    part = part.strip()
                    if ":" in part:
                        value = part.split(":")[-1].strip()
                        if value:
                            values.append(value)
            elif ":" in line:
                value = line.split(":")[-1].strip()
                if value:
                    values.append(value)

    with open(content_txt_path, "w", encoding="utf-8") as fh:
        for value in values:
            fh.write(f"{value}\n")

    print("=== ALL EXTRACTED VALUES ===")
    for value in values:
        print(value)

    repeating = {v: c for v, c in Counter(values).items() if c > 1}
    print("\n=== REPEATING VALUES ===")
    if repeating:
        for value, count in sorted(repeating.items(), key=lambda x: x[1], reverse=True):
            print(f"{value} (appears {count} times)")
    else:
        print("No repeating values found")

    print(f"\nSaved to {content_txt_path.name}  (in temp/ folder)")


if __name__ == "__main__":
    extract_values_from_md()
