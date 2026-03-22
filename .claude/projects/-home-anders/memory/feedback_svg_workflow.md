---
name: SVG asset workflow - extract from Figma, user uploads
description: Always extract SVGs from Figma and save locally for the user to upload to Webflow assets, never use JS-injected SVGs
type: feedback
---

When icons or SVG assets are needed, always extract them from Figma, save as clean SVG files locally, and ask the user to upload to Webflow assets. Then use proper Webflow Image elements with asset IDs.

**Why:** JS-injected SVGs are fragile and don't follow Webflow best practices. Proper Image elements with asset IDs survive renames and are managed by Webflow.

**How to apply:** 1) Get design context from Figma, 2) Download/create clean SVG files, 3) Save to local filesystem, 4) Ask user to upload to Webflow assets, 5) Use element_builder with set_image_asset to add as proper Image elements.
