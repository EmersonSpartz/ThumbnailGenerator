# Bug Retros — Thumbnail Generator v2

## 2026-03-16: gen_title saved as list, crashed all thumbnail rendering

**Bug class:** Type mismatch across data boundary + Silent error swallowing (patterns #2, #7)

**What broke:** `gen_title` was saved as a list (e.g., `["Title"]`) instead of a string. When the frontend called `.replace()` on it, it threw `displayTitle.replace is not a function`, which crashed the entire `forEach` loop in `loadTextTabHistory()`. Zero thumbnails rendered. The `catch(() => {})` silently swallowed the error, so the user just saw a blank page with no error message.

**Root cause chain:**
1. `job_manager.py` line 158 saved `job["params"]["titles"]` (a list) directly into `gen_title` without extracting the element
2. Frontend SSE handler also passed `batch.titles` (array) directly to `data._gen_title`
3. `addThumbnailCard()` called `.replace()` on what it assumed was always a string
4. The `.forEach` loop had no per-item try/catch, so one bad entry killed ALL rendering
5. The `catch(() => {})` at the end silently swallowed the error — user saw nothing

**Systemic fixes applied:**
- Added "Type mismatch across API/data boundary" to Common Runtime Bugs in MEMORY.md
- Added Pre-Ship Checklist item #11: verify JSON types match what JS expects at backend→frontend boundary
- Both fixes apply to ALL projects, not just thumbnail generator

**How it should have been caught:**
- Pre-Ship Checklist #7 (trace the full data path) would have caught this if the data *types* were checked, not just presence
- Pre-Ship Checklist #8 (check for JS runtime errors) would have caught it if the page was actually loaded after the change
- Any `catch` block that logged the error instead of silently swallowing would have made the bug visible immediately
