#!/usr/bin/env python3
"""extract_values — extract colon-separated values from content.md.

Reads ``source/content.md``, strips optional ``(font_size: Npx)`` markers,
and writes the extracted values (one per line) to
``generated/temp/content.txt``. Intended as the first step of the pipeline
to produce a simple token list used by downstream OCR helpers.

Usage:
        python pipeline/extract/extract_values.py
"""

import re
from collections import Counter
from pathlib import Path

_FONT_SIZE_RE = re.compile(r'\s*\(font_size\s*:\s*[0-9.]+\s*px\)\s*', re.IGNORECASE)


def _strip_font_size(value: str) -> str:
    return _FONT_SIZE_RE.sub('', value).strip()


def extract_values_from_md() -> None:
    """Read content.md, extract colon-separated values, write to generated/temp/content.txt."""
    workspace_root = Path(__file__).parent.parent.parent.resolve()
    content_md_path = workspace_root / "source" / "content.md"
    temp_dir = workspace_root / "generated" / "temp"
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
                    if " : " in part:
                        value = _strip_font_size(part.split(" : ", 1)[-1].strip())
                        if value:
                            values.append(value)
                    elif ":" in part:
                        value = _strip_font_size(part.split(":", 1)[-1].strip())
                        if value:
                            values.append(value)
            elif " : " in line:
                value = _strip_font_size(line.split(" : ", 1)[-1].strip())
                if value:
                    values.append(value)
            elif ":" in line:
                value = _strip_font_size(line.split(":", 1)[-1].strip())
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
