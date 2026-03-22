---
name: Always choose optimal solutions
description: Prefer proper fixes over workarounds, ask user to help in Webflow Designer when MCP has limitations
type: feedback
---

Always go for the optimal solution even if not supported by the MCP tools. Ask the user to perform manual actions in the Webflow Designer rather than using workarounds (like hiding elements with data-hide instead of deleting them).

**Why:** Workarounds add dead weight to the DOM and create confusion. The user is willing and able to do manual steps in the designer.

**How to apply:** When MCP can't properly execute something (e.g. transform_element_to_component not replacing the original, or inability to delete elements), explain what needs to be done and ask the user to do it manually in the Webflow Designer.
