---
name: "image-stitch"
description: "Stitches multiple overlapping screenshots into a single long image. Invoke when user needs to combine multiple screenshots or create long-scroll captures."
---

# Image Stitch Skill

Intelligently stitches multiple overlapping screenshots into a seamless long image.

## Core Capabilities

1. **Smart Overlap Detection**
   - Uses NCC (Normalized Cross-Correlation) algorithm
   - Finds optimal matching position between images
   - Handles varying overlap sizes

2. **Hard-Cut Merging**
   - Clean cut at overlap boundary (no blending)
   - Preserves image quality
   - Fast processing

3. **Batch Processing**
   - Process entire directories of screenshots
   - Automatic sorting by filename
   - Progress reporting

## Usage

### Python API

```python
from image_stitch import stitch_images, find_overlap_smart

# Stitch all images in a directory
result = stitch_images("/path/to/screenshots")

# Save result
cv2.imwrite("output.png", result)
```

### Command Line

```bash
# Stitch all PNGs in directory
python stitch.py /path/to/screenshots

# Output saved to: /path/to/screenshots/stitched/result_stitched.png
```

## Algorithm

1. **Overlap Detection**:
   - Search range: bottom 50% of image A, top 50% of image B
   - Coarse search (step=10) → Fine search (step=1)
   - Window size: 80px height
   - Metric: NCC (Normalized Cross-Correlation)

2. **Merge Strategy**:
   - Keep: Image A from top to overlap line
   - Keep: Image B from overlap line to bottom
   - Concatenate without blending

## Requirements

- OpenCV (cv2)
- NumPy
- PIL (optional, for format conversion)

## Input Requirements

- All images must have same width
- Images should have overlapping content
- Supported formats: PNG, JPG

## Output

- Single stitched image
- Preserves original quality
- Named: `result_stitched.png`
