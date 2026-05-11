---
name: "page-screenshot-to-html"
description: "Converts page screenshots to high-fidelity HTML code. Invoke when user wants to convert image screenshots to HTML, especially for mobile app UI screenshots."
---

# Page Screenshot to HTML

This skill converts page screenshots (especially mobile app UI screenshots) to high-fidelity HTML code.

## Core Principles

1. **Static Page Only**: Generate static HTML, NO animations, NO interactions, NO JavaScript
2. **Complete Content**: Show ALL content from the screenshot, NO scrolling, NO overflow:hidden
3. **Exact Dimensions**: Match original image dimensions exactly
4. **No Decorations**: NO added elements not in original (no extra shadows, borders, rounded corners)
5. **No Emoji**: Use SVG icons instead of emoji
6. **No Noise**: Filter out detected noise elements (random triangles, incomplete shapes)

## DPR (Device Pixel Ratio) Handling

- Physical pixels = CSS logical pixels × DPR
- iPhone 14: 1170px physical / 390px logical = 3x DPR
- All CSS dimensions must use logical pixels

## iOS Page Structure

- **Status Bar**: 24px logical (72px physical), top of page
- **Navigation Bar**: 44px logical (132px physical), below status bar
- **Content Area**: Below navigation bar to bottom
- **Bottom Button**: Fixed at bottom, not floating

## Prohibited Items

- NO transitions, animations, @keyframes
- NO hover effects, click events
- NO JavaScript
- NO emoji
- NO overflow: hidden or overflow-y: auto
- NO decorative elements not in original
- NO noise elements (small triangles, random shapes)

## Output Requirements

- Complete HTML code
- All content visible without scrolling
- Exact dimensions matching original
- Clean, static presentation
