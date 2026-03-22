---
name: Never hardcode CDN URLs for assets
description: Always use Webflow Image elements with asset IDs instead of hardcoded CDN URLs in JavaScript injection
type: feedback
---

Never hardcode CDN URLs for images or assets. Always use Webflow Image elements that reference assets by ID via the element_builder or ask the user to place them manually in the designer.

**Why:** CDN URLs change when assets are renamed, moved, or reprocessed. Hardcoded URLs create fragile dependencies that silently break.

**How to apply:** When adding images to Webflow, use `set_image_asset` with the asset ID in element_builder, or ask the user to place Image elements manually in the designer. Never inject `<img src="cdn.prod.website-files.com/...">` via JavaScript.
