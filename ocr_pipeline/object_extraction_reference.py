import cv2
import numpy as np

# Load image
image = cv2.imread("output/text_cleaned.png")
output = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# --- Step 1: Adaptive Threshold (better separation) ---
thresh = cv2.adaptiveThreshold(
    gray, 255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY_INV,
    11, 2
)

# --- Step 2: Light Morphology (remove noise, don't merge) ---
kernel = np.ones((2, 2), np.uint8)
clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

# --- Step 3: Edge Detection (preserve boundaries) ---
edges = cv2.Canny(gray, 50, 150)

# --- Step 4: Combine region + edge info ---
combined = cv2.bitwise_or(clean, edges)

# --- Step 5: Find contours ---
contours, _ = cv2.findContours(
    combined,
    cv2.RETR_EXTERNAL,
    cv2.CHAIN_APPROX_SIMPLE
)

detected_boxes = []

# --- Step 6: Filter and draw bounding boxes ---
for cnt in contours:
    area = cv2.contourArea(cnt)

    # Filter very small noise
    if area < 20:
        continue

    x, y, w, h = cv2.boundingRect(cnt)

    # Optional: filter very large region (sidebar)
    if w > 0.9 * image.shape[1] and h > 0.9 * image.shape[0]:
        continue

    detected_boxes.append((x, y, w, h))

    # Draw bounding box
    cv2.rectangle(output, (x, y), (x + w, y + h), (0, 0, 255), 1)

# --- Step 7: Show result ---
# cv2.imshow("Detected Objects", output)
# cv2.waitKey(0)
# cv2.destroyAllWindows()
cv2.imwrite("output/object_detected_reference.png", output)

# Print results
print(f"Total detected objects: {len(detected_boxes)}")