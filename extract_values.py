import re
from collections import Counter
from pathlib import Path

def extract_values_from_md():
    """
    Reads content.md file and extracts all values on the right side of colons.
    Handles piped formats and ignores lines starting with # and -.
    Saves output to temp/content.txt
    """
    
    values = []
    
    # Get workspace root and paths
    workspace_root = Path(__file__).parent.resolve()
    content_md_path = workspace_root / "content.md"
    temp_dir = workspace_root / "temp"
    content_txt_path = temp_dir / "content.txt"
    
    # Ensure temp directory exists
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Read the markdown file
    with open(content_md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Process each line
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Remove leading markdown symbols (# and -)
        if line.startswith('#'):
            line = line.lstrip('#').strip()
        elif line.startswith('-'):
            line = line[1:].strip()
        
        # Check if line contains pipes (multiple colon-separated values)
        if '|' in line:
            # Split by pipes and process each part
            parts = line.split('|')
            for part in parts:
                part = part.strip()
                if ':' in part:
                    # Extract value after the last colon
                    value = part.split(':')[-1].strip()
                    if value:
                        values.append(value)
        else:
            # Single colon format
            if ':' in line:
                # Extract value after the colon
                value = line.split(':')[-1].strip()
                if value:
                    values.append(value)
    
    # Count occurrences of each value
    value_counts = Counter(values)
    
    # Find repeating values (appearing more than once)
    repeating_values = {value: count for value, count in value_counts.items() if count > 1}
    
    # Write extracted values to temp/content.txt
    with open(content_txt_path, 'w', encoding='utf-8') as out_f:
        for value in values:
            out_f.write(f"{value}\n")
    
    # Print all extracted values to console
    print("=== ALL EXTRACTED VALUES ===")
    for value in values:
        print(value)
    
    # Print repeating values to console
    print("\n=== REPEATING VALUES ===")
    if repeating_values:
        for value, count in sorted(repeating_values.items(), key=lambda x: x[1], reverse=True):
            print(f"{value} (appears {count} times)")
    else:
        print("No repeating values found")
    
    print(f"\n✓ Saved to {content_txt_path.name}  (in temp/ folder)")

if __name__ == "__main__":
    extract_values_from_md()
