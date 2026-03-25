#!/usr/bin/env python3
"""
Deep cleanup script - removes identified unused/misplaced files and directories
"""

import shutil
import os
from pathlib import Path

workspace = Path(__file__).parent

# Files and directories to remove
ITEMS_TO_REMOVE = [
    # Dead debug files
    "pipeline/render/test_path.py",
    
    # Empty artifacts
    "1",
    
    # Duplicate/misplaced generated files
    "pipeline/generated/optimize_logs.csv",
    "pipeline/generated/temp",
    "pipeline/generated",  # Remove after temp is gone
    
    # Analysis documents (auto-generated during analysis)
    "CLEANUP_GUIDE.md",
    "FILE_STATUS_MATRIX.md",
    "WORKSPACE_ANALYSIS.md",
    
    # Build artifacts and caches
    ".mypy_cache",
    "pipeline/__pycache__",
]

def cleanup():
    """Execute cleanup with detailed reporting"""
    print("\n" + "="*70)
    print("DEEP CLEANUP - Removing unused/misplaced files")
    print("="*70 + "\n")
    
    removed_count = 0
    errors = []
    
    for item in ITEMS_TO_REMOVE:
        path = workspace / item
        
        if not path.exists():
            print(f"  - {item:40} [SKIPPED - not found]")
            continue
        
        try:
            if path.is_dir():
                shutil.rmtree(path)
                print(f"  ✓ {item:40} [DIR REMOVED]")
            else:
                os.remove(path)
                print(f"  ✓ {item:40} [FILE REMOVED]")
            removed_count += 1
        except Exception as e:
            error_msg = f"{item}: {str(e)}"
            errors.append(error_msg)
            print(f"  ✗ {item:40} [ERROR: {str(e)}]")
    
    print("\n" + "="*70)
    print(f"Results: {removed_count} items removed", end="")
    if errors:
        print(f", {len(errors)} errors")
        print("\nErrors:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("\n✅ Cleanup successful - no errors")
    
    print("="*70 + "\n")
    
    # Show remaining structure
    print("📁 Remaining workspace structure:\n")
    for item in sorted(os.listdir(workspace)):
        if item.startswith('.'):
            continue
        path = workspace / item
        if path.is_dir():
            print(f"  📂 {item}/")
        else:
            size = path.stat().st_size
            size_str = f"{size/1024:.1f}KB" if size > 1024 else f"{size}B"
            print(f"  📄 {item:40} ({size_str})")

if __name__ == "__main__":
    cleanup()
