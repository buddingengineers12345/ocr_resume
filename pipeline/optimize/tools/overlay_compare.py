"""overlay_compare — DEPRECATED: Use pipeline/optimize/visual_comparison.py instead.

**DEPRECATION NOTICE:**

This module has been MERGED into `visual_comparison.py` (pipeline/optimize/).

All functionality from this file is now available in the consolidated module:
- Alpha-blended overlays (configurable transparency) ✓
- Side-by-side comparisons ✓
- Difference heatmaps with statistics ✓
- Plus additional features from visual_comparison.py

**Migration guide:**
  OLD: python pipeline/optimize/tools/overlay_compare.py
  NEW: python pipeline/optimize/visual_comparison.py

The new module includes:
- ALPHA_BLEND_FACTORS = [0.3, 0.5, 0.7] → multiple alpha levels
- LABEL_IMAGES = True → labels on side-by-side
- GAP_SEPARATOR = 20 → configurable gap
- Better error handling and statistics

**This file is kept for reference only. DO NOT USE.**

See pipeline/optimize/visual_comparison.py for the unified implementation.
"""

# NOTE: This file is deprecated. Import and use visual_comparison.py instead.
