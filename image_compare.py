"""
Image processing script to perform logical and mathematical operations on images.
"""

import cv2
import numpy as np
from pathlib import Path

# Create output directory if it doesn't exist
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

# Load images
print("Loading images...")
img1 = cv2.imread("output/text_cleaned.png")
img2 = cv2.imread("image_reference/Page_1.png")

if img1 is None or img2 is None:
    print("Error: Could not load one or both images")
    exit(1)

print(f"Image 1 shape: {img1.shape}")
print(f"Image 2 shape: {img2.shape}")

# Resize img2 to match img1 if needed
if img1.shape != img2.shape:
    print(f"Resizing image 2 from {img2.shape} to {img1.shape}")
    img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

# Convert to grayscale for logical operations
gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

# Convert to binary (threshold at 127)
_, bin1 = cv2.threshold(gray1, 127, 255, cv2.THRESH_BINARY)
_, bin2 = cv2.threshold(gray2, 127, 255, cv2.THRESH_BINARY)

print("Performing image operations...")

# 1. OR operation (logical OR)
or_result = cv2.bitwise_or(bin1, bin2)
cv2.imwrite("output/compare_or.png", or_result)
print("✓ Saved compare_or.png")

# 2. AND operation (logical AND)
and_result = cv2.bitwise_and(bin1, bin2)
cv2.imwrite("output/compare_and.png", and_result)
print("✓ Saved compare_and.png")

# 3. XOR operation
xor_result = cv2.bitwise_xor(bin1, bin2)
cv2.imwrite("output/compare_xor.png", xor_result)
print("✓ Saved compare_xor.png")

# 4. Difference (absolute difference)
diff_result = cv2.absdiff(gray1, gray2)
cv2.imwrite("output/compare_diff.png", diff_result)
print("✓ Saved compare_diff.png")

# 5. Add operation (saturated addition)
add_result = cv2.add(gray1, gray2)
cv2.imwrite("output/compare_add.png", add_result)
print("✓ Saved compare_add.png")

# 6. Subtract operation
sub_result = cv2.subtract(gray1, gray2)
cv2.imwrite("output/compare_subtract.png", sub_result)
print("✓ Saved compare_subtract.png")

# 7. Weighted blend (50/50)
blend_result = cv2.addWeighted(img1, 0.5, img2, 0.5, 0)
cv2.imwrite("output/compare_blend_50_50.png", blend_result)
print("✓ Saved compare_blend_50_50.png")

# 8. Average
avg_result = (img1.astype(np.float32) + img2.astype(np.float32)) / 2
avg_result = np.uint8(np.clip(avg_result, 0, 255))
cv2.imwrite("output/compare_average.png", avg_result)
print("✓ Saved compare_average.png")

# 9. Min (pixelwise minimum)
min_result = np.minimum(img1, img2)
cv2.imwrite("output/compare_min.png", min_result)
print("✓ Saved compare_min.png")

# 10. Max (pixelwise maximum)
max_result = np.maximum(img1, img2)
cv2.imwrite("output/compare_max.png", max_result)
print("✓ Saved compare_max.png")

# 11. NOT operation on first image
not_result = cv2.bitwise_not(bin1)
cv2.imwrite("output/compare_not.png", not_result)
print("✓ Saved compare_not.png")

# 12. Inverted difference
inv_diff = cv2.absdiff(bin1, bin2)
cv2.imwrite("output/compare_inv_diff.png", inv_diff)
print("✓ Saved compare_inv_diff.png")

print("\nAll comparisons completed successfully!")
print(f"Output images saved to {output_dir}/compare_*.png")
