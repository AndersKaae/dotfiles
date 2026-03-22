---
name: Ask before mutating migration data
description: Always ask user before adding fallbacks or default values that change the migrated data
type: feedback
---

When migration data is missing or unexpected, ask the user how to handle it rather than silently adding fallbacks or defaults. Data integrity decisions should always be confirmed.

**Why:** The user wants full control over what gets migrated and how. Silent fallbacks can introduce incorrect data.
**How to apply:** When a field is missing/null during migration, report it and ask the user what value to use or whether to skip the item.
