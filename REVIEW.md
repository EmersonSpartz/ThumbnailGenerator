# Code Review Rules — Thumbnail Generator

These patterns have each caused real production bugs. Check every diff against them before deploying.

## Critical (must fix before deploy)

### 1. video_name missing from history writes
Every `job_manager.add_result()` call must include `'video_name': video_name`.
Missing this means thumbnails are untagged and won't appear when filtering by video.
**grep check**: `grep -n "add_result" app.py` — every call must have video_name in the dict.

### 2. Batch loop passing total count to LLM
Any loop that calls `generate_concepts_and_prompts_streaming()` must pass
`count=min(batch_size, total - generated_so_far)`, NOT `count=total`.
Passing 50 to a 32k-token API silently truncates JSON.

### 3. UI context not cleared on switch
Any function that switches "current context" (video, project) must clear
the display container BEFORE calling the load function.
A guard like `if (container.children.length > 0) return` prevents reload on switch.

### 4. History filter including untagged records
`job_manager.get_history()` filter must be strict: `video_name == requested_video`.
Never add `or not video_name` — that bleeds every old untagged thumbnail into every video.

### 5. Type mismatch at API boundary
If a field can be a list OR string (e.g. gen_title), coerce it at the boundary:
`String(Array.isArray(v) ? v[0] || '' : v)`
Python lists become JS arrays — calling `.replace()` on an array crashes silently.

### 6. Disk space before writing files
Any endpoint that writes image files should fail gracefully when disk is low,
not crash with `[Errno 28] No space left on device`.
Check `/api/disk-usage` free_mb > 50 in pre-generation validation.

## Important (flag for review)

### 7. SSE endpoints without try/catch around JSON.parse
Every `eventSource.onmessage` handler must wrap `JSON.parse(event.data)` in try/catch.
A malformed SSE event kills the entire stream handler.

### 8. New endpoint missing video_name requirement
Any new generation endpoint must call `_require_video_name()` at the top,
or explicitly document why it doesn't need one.

### 9. Cleanup deleting referenced files
Any `shutil.rmtree` or file deletion must check that no favorites/history records
reference files inside the deleted path.
Favorites are safe to delete from output/ because copy-on-save backs them up to data/favorites_images/.

### 10. Health check returning 500
The `/api/health` endpoint must ALWAYS return 200, even under disk pressure.
A 500 health check causes Railway to kill the container → infinite crash loop.

## Skip / known false positives
- `or not video_name` in `get_favorites()` — intentional, favorites predate video system
- `count=count` in single-call endpoints (not batch loops) — fine for one-shot generation
- `shutil.copy2` in favorites protected dir — intentional copy, not deletion
