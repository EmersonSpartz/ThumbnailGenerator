# QA Report — Thumbnail Generator v2
**Date:** 2026-03-13
**Overall:** ISSUES FOUND

---

## Critical Issues

None. Server is running, all core generation endpoints are accessible.

---

## Bugs

### 1. `/api/rubric` returns 404
The task prompt (and likely any documentation/links) references `/api/rubric`, but the actual endpoint is `/api/get-rubric`. There is no route registered at `/api/rubric`.

**Reproduce:**
```
curl http://localhost:5050/api/rubric
# → 404 Not Found
curl http://localhost:5050/api/get-rubric
# → 200 OK with rubric content
```

**Impact:** Any external script, curl command, or documentation pointing to `/api/rubric` will silently fail. Low impact in practice since users access rubric through the UI, but worth aliasing.

---

### 2. Favorites POST accepts empty body and creates hollow records
`POST /api/favorites` with an empty JSON body `{}` succeeds with HTTP 200 and creates a favorite record with all fields blank (`thumbnail_path`, `prompt`, `concept_name` all empty). Two such hollow records already exist in the database (ids 2 and 4).

**Reproduce:**
```
curl -X POST -H "Content-Type: application/json" -d '{}' http://localhost:5050/api/favorites
# → 200 OK, creates empty favorite
```

**Impact:** Pollutes the favorites list and patterns analysis with empty records. The favorites API already returns these hollow entries mixed with real ones.

---

### 3. `/api/prompts/<key>` returns 200 with empty value for unknown keys (no 404)
Requesting a non-existent prompt key returns HTTP 200 with `{"key": "...", "value": ""}` instead of a 404. A caller cannot distinguish "key exists but is empty" from "key does not exist."

**Reproduce:**
```
curl http://localhost:5050/api/prompts/nonexistent_key_xyz123
# → {"key": "nonexistent_key_xyz123", "value": ""}  HTTP 200
```

**Impact:** Low — only relevant if code logic checks for key existence. UI-only callers are unaffected.

---

## Quality Issues

### 4. Template count is 29, not the expected "29 ALL_TEMPLATES" from the task
Template count matches: 14 defaults + 15 extras = 29 total. DEFAULT_COUNT = 14. Both numbers match what was expected. No issue here — this is a pass.

---

## Passed Checks

| Check | Result |
|---|---|
| `GET /` returns 200 | PASS |
| `GET /api/videos` returns 200 with video list | PASS |
| `GET /api/history` returns 200 with sessions array | PASS |
| `GET /api/favorites` returns 200 with favorites + patterns | PASS |
| `GET /api/get-rubric` returns 200 with full rubric text | PASS |
| `GET /api/prompts` returns 200 | PASS |
| `GET /api/models` returns 200 with 6 models listed | PASS |
| `GET /api/health` returns `{"status": "ok"}` | PASS |
| `GET /api/templates` returns 200 | PASS |
| `GET /api/last-shootout` returns 200 | PASS |
| `GET /api/live-stream` connects and returns SSE data | PASS |
| Wrong HTTP method on read endpoints returns 405 | PASS |
| Non-existent routes return 404 | PASS |
| `DELETE /api/favorites/999999` (non-existent) returns `{"success": false}` | PASS |
| `#video-bar` present in homepage HTML | PASS |
| `#batch-queue-container` present in homepage HTML | PASS |
| `#model-checkboxes` present in homepage HTML | PASS |
| Favorites tab (`data-tab="favorites"`) present | PASS |
| `ALL_TEMPLATES` JS array present in homepage | PASS |
| `#video-modal-overlay` present in homepage HTML | PASS |
| Video modal shows on first visit (no video selected → `showVideoModal()` called in `loadVideoList`) | PASS |
| ALL_TEMPLATES count = 29 (14 default + 15 extras) | PASS |
| DEFAULT_COUNT = 14 | PASS |
| Form field persistence via localStorage | PASS |
| Batch directions persistence via localStorage | PASS |

---

## Summary

The app is healthy and all core functionality is intact. Three bugs found:

1. **`/api/rubric` 404** — wrong path; real path is `/api/get-rubric`
2. **Favorites accepts empty POST** — creates hollow DB records; needs validation on required fields
3. **Prompts unknown key returns 200** — should return 404 for missing keys to distinguish "empty" from "absent"
