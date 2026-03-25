#!/usr/bin/env python3
"""extract_values — extract colon-separated values from content.md.

**Purpose:**
Parses markdown content file to extract plain-text values, stripping font size
markers, and generates a normalized token list. This is the first preprocessing
step for downstream OCR matching and reference word validation.

**Workflow:**
1. Read source/content.md line by line
2. Skip lines starting with '#' (extract header content, not prefix)
3. Skip lines starting with '-' (extract bullet content, not prefix)
4. Split on pipes '|' and colons ':' to find colon-separated values
5. Strip font_size markers "(font_size: Npx)" from all values
6. Write extracted values (one per line) to generated/temp/content.txt
7. Print summary showing all values and repeating tokens

**Input files:**
- source/content.md: Markdown with optional font size annotations

**Output files:**
- generated/temp/content.txt: One extracted value per line (no markers)

**Usage:**
    python pipeline/extract/extract_values.py
"""

import re
from collections import Counter
from pathlib import Path

_FONT_SIZE_RE = re.compile(r'\s*\(font_size\s*:\s*[0-9.]+\s*px\)\s*', re.IGNORECASE)


def _strip_font_size(value: str) -> str:
    """Remove font_size markers from a string.
    
    Strips patterns like "(font_size: 32px)" or "(FONT_SIZE: 14.5px)" from text.
    Case-insensitive to handle various formatting styles.
    """
    return _FONT_SIZE_RE.sub('', value).strip()


def extract_values_from_md() -> None:
    """Extract normalized values from markdown and write token list to file.
    
    **Processing steps:**
    1. Read each line from source/content.md
    2. Skip empty lines
    3. For lines starting with '#' or '-', extract header/bullet content only
    4. Split pipe-delimited content to find independent values
    5. Split colon-delimited pairs to extract right-hand values (e.g., "Name : John Doe" → "John Doe")
    6. Strip font_size markers from all values
    7. Write clean values to generated/temp/content.txt (one per line)
    8. Display summary statistics showing all values and repeating tokens
    
    **Output:**
    - Creates generated/temp/ directory as needed
    - Writes content.txt with newline-separated values
    - Prints all extracted values and highlights repeating ones
    """
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
