"""css_manager — safe read/patch/restore helper for template.css.

Provides an API to snapshot, modify and restore selector-scoped CSS
properties in ``source/template.css``. Changes are written atomically and a
snapshot stack supports easy rollback during optimization experiments.

Supported helpers include numeric extraction, padding shorthand helpers and
batch apply/delta semantics used by the optimizer.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

# ── Default path ──────────────────────────────────────────────────────────────
WORKSPACE    = Path(__file__).parent.parent.parent.resolve()
TEMPLATE_CSS = WORKSPACE / "source" / "template.css"


# ── Snapshot ──────────────────────────────────────────────────────────────────

class CSSManager:
    """
    Manages reads and writes to template.css.
    Instantiate once; the snapshot stack handles rollback.
    """

    def __init__(self, css_path: Path = TEMPLATE_CSS):
        self.css_path = css_path
        self._snapshots: list[str] = []

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _read(self) -> str:
        return self.css_path.read_text(encoding="utf-8")

    def _write(self, content: str) -> None:
        """Atomic write: write to temp file then rename."""
        fd, tmp = tempfile.mkstemp(
            dir=self.css_path.parent, prefix=".css_tmp_", suffix=".css"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, self.css_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ── Snapshot stack ────────────────────────────────────────────────────────

    def snapshot(self) -> str:
        """Save current CSS content and return it (also pushed to stack)."""
        content = self._read()
        self._snapshots.append(content)
        return content

    def restore(self, content: Optional[str] = None) -> None:
        """
        Restore CSS to *content* (if provided) or pop and restore from stack.
        """
        if content is not None:
            self._write(content)
            return
        if self._snapshots:
            self._write(self._snapshots.pop())

    def restore_to_base(self) -> None:
        """Restore all the way back to the first snapshot."""
        if self._snapshots:
            self._write(self._snapshots[0])
            self._snapshots.clear()

    # ── Block extraction ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_block(css: str, selector: str) -> tuple[str, int, int]:
        """
        Find the CSS block for *selector* and return (block_text, start, end).
        Handles selectors with spaces, '#', '.', ':' etc.
        Only matches the FIRST occurrence (sufficient for this template).
        Raises ValueError if not found.
        """
        # Escape the selector for use in regex
        esc = re.escape(selector.strip())
        # Match selector followed by optional whitespace, then '{'
        pattern = rf"{esc}\s*\{{([^}}]*)\}}"
        m = re.search(pattern, css, re.DOTALL)
        if m is None:
            raise ValueError(f"CSS selector not found: {selector!r}")
        return m.group(0), m.start(), m.end()

    # ── Generic get / set ─────────────────────────────────────────────────────

    def get_value(self, selector: str, prop: str) -> Optional[str]:
        """
        Return the raw CSS value string for *prop* inside *selector*, or None.
        E.g. get_value('#main', 'padding-top') → '59px'
        """
        css = self._read()
        try:
            block, _, _ = self._extract_block(css, selector)
        except ValueError:
            return None

        # Match property: value;  (value may contain spaces, px, etc.)
        m = re.search(
            rf"(?:^|;|\{{)\s*{re.escape(prop)}\s*:\s*([^;}}]+?)(?:\s*;|\s*\}})",
            block,
            re.MULTILINE | re.DOTALL,
        )
        return m.group(1).strip() if m else None

    def get_numeric(self, selector: str, prop: str) -> Optional[float]:
        """
        Return the first numeric value from the property as a float, or None.
        E.g. ``margin-bottom: 4px`` → 4.0
        """
        val = self.get_value(selector, prop)
        if val is None:
            return None
        m = re.search(r"[-+]?\d+(?:\.\d+)?", val)
        return float(m.group(0)) if m else None

    def set_value(self, selector: str, prop: str, new_value) -> bool:
        """
        Set *prop* inside *selector* to *new_value*.
        *new_value* can be a number (auto-units inferred) or a string.
        Returns True on success.

        Infers units:
          - str  → used verbatim
          - int  → appended 'px'  (for most dimension properties)
          - float with abs < 10 → unitless (for line-height etc.)
          - float with abs ≥ 10 → appended 'px'
        """
        new_value_str = _format_value(prop, new_value)

        css = self._read()
        try:
            block_old, start, end = self._extract_block(css, selector)
        except ValueError:
            return False

        # Replace the property value inside the block
        block_new, n = re.subn(
            rf"(?<=[\{{;])\s*({re.escape(prop)}\s*:\s*)[^;}}]+?(\s*(?:;|\}}|\Z))",
            lambda m_: f" {m_.group(1)}{new_value_str}{m_.group(2)}",
            block_old,
            count=1,
            flags=re.DOTALL,
        )

        if n == 0:
            # Property not yet present in block – append before closing brace
            block_new = block_old.rstrip().rstrip("}") + f"\n  {prop}: {new_value_str};\n}}"

        new_css = css[:start] + block_new + css[end:]
        self._write(new_css)
        return True

    # ── Padding shorthand helpers ─────────────────────────────────────────────

    def get_padding_side(self, selector: str, side: str) -> Optional[float]:
        """
        Return a single padding side value (top/right/bottom/left) from the
        ``padding`` shorthand, or from a ``padding-<side>`` longform property.
        Returns px value as float, or None.
        """
        # Try longform first
        longform = self.get_numeric(selector, f"padding-{side}")
        if longform is not None:
            return longform

        # Fall back to shorthand
        val = self.get_value(selector, "padding")
        if val is None:
            return None
        parts = val.split()
        nums = []
        for p in parts:
            m = re.match(r"([-+]?\d+(?:\.\d+)?)(?:px)?", p)
            if m:
                nums.append(float(m.group(1)))

        SIDE_INDEX = {"top": 0, "right": 1, "bottom": 2, "left": 3}
        idx = SIDE_INDEX.get(side)
        if idx is None or not nums:
            return None

        # CSS shorthand expansion rules
        if len(nums) == 1:
            return nums[0]
        elif len(nums) == 2:
            return nums[0] if idx in (0, 2) else nums[1]
        elif len(nums) == 3:
            if idx == 0: return nums[0]
            if idx in (1, 3): return nums[1]
            return nums[2]
        else:  # 4 values
            return nums[idx]

    def set_padding_side(
        self, selector: str, side: str, new_px: float
    ) -> bool:
        """
        Set a single padding side by **rewriting the shorthand to 4-value form**
        so individual sides can be patched independently.
        Returns True on success.
        """
        # Collect all 4 sides
        sides = ["top", "right", "bottom", "left"]
        values = {}
        for s in sides:
            v = self.get_padding_side(selector, s)
            values[s] = v if v is not None else 0.0
        values[side] = float(new_px)

        # Build 4-value shorthand
        new_padding = (
            f"{int(values['top'])}px "
            f"{int(values['right'])}px "
            f"{int(values['bottom'])}px "
            f"{int(values['left'])}px"
        )
        return self.set_value(selector, "padding", new_padding)

    # ── Bulk apply ────────────────────────────────────────────────────────────

    def apply_batch(self, patches: list[tuple]) -> int:
        """
        Apply a list of (selector, prop, value) tuples atomically (one
        read-modify-write per call, but the full batch is written at the end).
        Returns number of successful patches.
        """
        css = self._read()
        n_ok = 0
        for selector, prop, value in patches:
            new_value_str = _format_value(prop, value)
            try:
                block_old, start, end = self._extract_block(css, selector)
            except ValueError:
                continue

            block_new, n = re.subn(
                rf"(?<=[\{{;])\s*({re.escape(prop)}\s*:\s*)[^;}}]+?(\s*(?:;|\}}|\Z))",
                lambda m_, nv=new_value_str: f" {m_.group(1)}{nv}{m_.group(2)}",
                block_old,
                count=1,
                flags=re.DOTALL,
            )

            if n == 0:
                block_new = block_old.rstrip().rstrip("}") + f"\n  {prop}: {new_value_str};\n}}"

            css = css[:start] + block_new + css[end:]
            # Re-read offsets are invalidated; rebuild block for next patch
            # by working on the updated css string directly.
            n_ok += 1

        self._write(css)
        return n_ok

    # ── Convenience delta apply ───────────────────────────────────────────────

    def delta(self, selector: str, prop: str, delta: float) -> Optional[float]:
        """
        Add *delta* to the current numeric value of *prop* in *selector*.
        Returns the new value, or None if the property could not be found.
        """
        curr = self.get_numeric(selector, prop)
        if curr is None:
            return None
        new_val = curr + delta
        self.set_value(selector, prop, new_val)
        return new_val

    def delta_padding_side(
        self, selector: str, side: str, delta: float
    ) -> Optional[float]:
        curr = self.get_padding_side(selector, side)
        if curr is None:
            return None
        new_val = curr + delta
        self.set_padding_side(selector, side, new_val)
        return new_val


# ── Value formatting helper ───────────────────────────────────────────────────

_UNITLESS_PROPS = {
    "line-height", "opacity", "z-index", "font-weight", "flex",
    "flex-grow", "flex-shrink", "order",
}


def _format_value(prop: str, value) -> str:
    """Convert a numeric or string value to a CSS value string."""
    if isinstance(value, str):
        return value
    prop_lower = prop.lower()
    if prop_lower in _UNITLESS_PROPS:
        return str(round(float(value), 3))
    if isinstance(value, int):
        return f"{value}px"
    # float
    fv = float(value)
    if abs(fv) < 10 and prop_lower == "line-height":
        return str(round(fv, 3))
    return f"{round(fv, 1)}px"


# ── CLI smoke-test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mgr = CSSManager()
    print("Current values in template.css:")
    tests = [
        ("#main",        "padding-top"),
        ("#main",        "padding-left"),
        (".photo-wrap",  "padding-bottom"),
        ("#sb-contact",  "padding"),
        ("#sb-awards",   "padding"),
        (".crow",        "margin-bottom"),
        (".arow",        "margin-bottom"),
        (".proj-list li","margin-bottom"),
        (".proj-list li","line-height"),
        (".job",         "margin-bottom"),
        (".pill",        "margin-bottom"),
    ]
    for sel, prop in tests:
        val = mgr.get_value(sel, prop)
        print(f"  {sel:<22} {prop:<22} → {val}")
