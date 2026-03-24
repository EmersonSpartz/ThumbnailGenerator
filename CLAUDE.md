# Thumbnail Generator v2

## Getting Current Context

**Run this first**: `python3 context.py`

Generates fresh context from actual codebase state (active models, API keys, recent changes). Always accurate, never stale.

For recent decisions/changes: Grep session memory at `~/.claude/projects/-Users-emersonspartz/*/session-memory/summary.md`

## Core Concepts

**What**: YouTube thumbnail generator for Species channel (premium, non-clickbait aesthetic)
**User**: Emerson is non-technical - do all technical work (configs, commands, API keys)
**Server**: `python app.py` on localhost:5050
**Architecture**: Flask + SSE streaming, multiple AI image models, Claude for ideation

## Agentic Mode (NEW)

**What**: AI-powered iterative thumbnail refinement - automatically improves quality through multiple iterations
**How it works**:
1. Generate initial thumbnails with selected models
2. Claude evaluates each thumbnail (0-10 quality score)
3. If below threshold, Claude refines the prompt and regenerates
4. Repeats until quality threshold met or max iterations reached

**Files**:
- Backend: `lib/agentic_refiner.py` (AgenticImageRefiner class)
- Endpoint: `/api/agentic-generate` in `app.py`
- Frontend: Checkbox toggle in settings panel (~line 1195)
- **Rubric: `rubric.txt`** - Edit this file to tweak evaluation criteria (server restart required)

**Settings**:
- Max iterations: 1-5 (default 2 = see before/after)
- Quality threshold: IGNORED - always iterates full max_iterations for continuous improvement

**UI** (Optimized for rapid rubric iteration):
- **Prominent Rubric Editor**: Always visible at top when agentic mode runs - edit criteria in real-time
- **Before/After Comparison Panel**: Shows iteration 1 | iteration 2 side-by-side with scores, prompts, and ↗️/↘️ indicators
- **Stats Summary**: Total concepts, % improved/worse/same, average score change
- **Prompt Diff Highlighting**: Green highlights show what changed between iterations
- **Re-evaluate Button**: Test rubric changes on existing images without regenerating (instant feedback)
- **Analysis Panel**: Detailed Claude reasoning for each evaluation
- **Auto-scroll**: Page automatically scrolls to rubric editor when generation starts

**Workflow** (Fast rubric iteration):
1. Generate thumbnails with agentic mode (auto-scrolls to rubric)
2. See before/after comparisons with Claude's scores and reasoning
3. Edit rubric directly (no "Show" button needed - always visible)
4. Click "Save Rubric" → "Re-evaluate" to see score changes instantly
5. Iterate until rubric feels right

**Persistence**: All agentic results now save to history automatically via job_manager integration

**Evaluation Criteria** (Research-based, 0-10 total):
1. **Scroll-Stopping Power (0-3)** - Bold colors, visual hierarchy, mobile readability, "moment of awe"
2. **Emotional Hook (0-2)** - Visible emotion OR mysterious element, Veritasium's "info gap" principle
3. **Visual Execution (0-2)** - Professional quality, clean composition, BBC/NatGeo aesthetic
4. **Text (0-2)** - Under 12 characters (proven best practice), high contrast, adds value
5. **Thumbnail-Specific (0-1)** - Works at YouTube size, distinct, clear without title

**Research Sources**: A/B testing shows bold colors increase CTR 20-30%, faces with emotion add 20-30%, under 12 chars outperforms text-heavy designs

**Quality Optimizations**:
- ⚡ Parallel image generation (all models at once via ThreadPoolExecutor)
- ⚡ Batch evaluation (single Claude API call for all images)
- 🎯 **Opus 4.6 for evaluations** (best reasoning, most impactful refinements)
- 🎯 **Aggressive refinement prompts** (demands bold, specific, visually dramatic changes)
- 🎯 **Always iterates** (no early stopping - continuous improvement)

## Key Pattern: Adding Image Generators

All generators inherit from `ImageGeneratorBase` with:
- `generate(prompt_data: dict, batch_id: str) -> dict`
- Returns: `{"success": bool, "file_path": str, "prompt_used": str, "model": str}`

To add a model:
1. Create class in `lib/image_generator.py`
2. Register in `MultiModelGenerator.__init__` (check for API key)
3. Export in `lib/__init__.py`
4. Add to `app.py` model_info dict
5. Add to **all 4** checkbox sections in `templates/index.html`:
   - `#shootout-model-checkboxes` (~line 315)
   - `#model-checkboxes` (~line 1030)
   - `#full-model-checkboxes` (~line 1265)
   - `#var-model-checkboxes` (~line 1665)
6. Add API key to `.env`
7. Restart server

## Export to Tester (2026-03-11)

**What**: One-click export of favorites to the Thumbnail Tester app for ELO voting
**How**: Firebase JS SDK added to `templates/index.html` (module script at bottom)
**Flow**: Favorites tab → "Export to Tester" button → enter video title → uploads to Firebase → returns voting link
**Firebase project**: `thumbnail-tester-b1746` (same as all tester apps)
**Tester URL**: `https://thumbnail-tester-b1746.web.app/thumbnail-tester/?v={videoId}`

## Stress Testing

**Script**: `./stress-test.sh [batches] [concepts_per_batch] [models]`
**Example**: `./stress-test.sh 20 10 gemini,flux` — 200 images across 20 batches
**Proven**: 10 batches × 5 concepts × gemini = 50/50 images, 0 failures (2026-03-11)

## Retry & Resilience (2026-03-11)

- All Claude API calls use `max_retries=3` (SDK built-in) + manual `_stream_with_retry()` with exponential backoff
- Non-streaming calls (generate_concepts, generate_prompts, generate_variations) retry on connection/rate limit errors
- Streaming calls use SDK retry only
- `multi_ideator.py`: each LLM future wrapped in try/catch (one failure doesn't crash batch)
- `job_manager.py`, `prompt_manager.py`: atomic file writes (tempfile + fsync + rename)
- `app.py`: `executor.shutdown(wait=True)` in agentic endpoint

## Verify Before Done (3 Levels)

### Level 1: verify.sh (after every code change)
**Run `./verify.sh`**. Checks imports, lib modules, server startup, and key endpoints. Takes ~5 seconds.

### Level 2: Browser QA via Chrome (MANDATORY after EVERY deploy)
After deploying ANY change (frontend OR backend — backend changes break frontend too):

1. Open the Railway URL in Chrome (via Chrome MCP tools)
2. Run the embedded QA test suite:
   ```
   window.__runQA().then(r => JSON.stringify(r, null, 2))
   ```
3. ALL tests must pass. Fix any failures before declaring done.
4. Then USE THE APP like Emerson would — switch videos, check hearts, verify fields persist.

**Why this exists:** 28+ bugs reached Emerson because they were browser-level behavioral bugs invisible to curl/API testing. Hearts disappearing, history not loading on video switch, fields not persisting — these only manifest in a real browser.

The `__runQA()` function tests all known failure patterns from bug-retros.md (18 tests):
- JS globals intact (no runtime crashes)
- Favorites cache loaded before cards render (race condition fix)
- Video selected (prevents untagged thumbnails)
- Hearts match favorites state
- Key UI elements present, tabs exist
- Disk space adequate for generation
- API health, history, favorites endpoints working
- Species style dropdown has a value
- No broken images on page
- Per-video field persistence (includes Generate tab)
- Deploy version validation (prevents testing cached old code)
- Favorites cache matches disk truth (in-memory ≠ disk detection)
- Server responsive (SSE endpoint reachable)
- localStorage not stale (detects old-format keys blocking new features)
- Generate button interactive (not hidden/disabled by JS crash)

### Level 3: Scale testing
Run `./stress-test.sh 5 10 gemini` (~5min) before declaring generation reliable.

## Multi-Session Coordination (CRITICAL)

Emerson often runs 2+ Claude sessions on this project. See global CLAUDE.md for full system.

**Quick version**: On session start, register and check for other sessions. You'll get an animal name (Fox, Owl, etc.). Introduce yourself to Emerson by that name. Before editing any file, check the lock. If another session owns it, work on something else.

**Deploy rule**: Only one session deploys. Check `bash ~/.claude/hooks/session-coord.sh status` before `railway up`.

## Important Rules

- **Quality > cost**: Cost irrelevant, optimize for thumbnail quality
- **No clickbait**: Species is premium content, avoid clickbait-trained models
- **Server restarts**: Always restart after backend changes: `kill $(lsof -ti :5050) && venv/bin/python app.py > /tmp/flask.log 2>&1 &`
- **Checkbox sync**: Keep all 4 frontend sections identical
- **Be proactive**: After finishing tasks, look for obvious improvements and make them
- **Update this file**: When making architectural changes, update CLAUDE.md immediately
