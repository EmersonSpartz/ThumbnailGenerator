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

## Important Rules

- **Quality > cost**: Cost irrelevant, optimize for thumbnail quality
- **No clickbait**: Species is premium content, avoid clickbait-trained models
- **Server restarts**: Always restart after backend changes: `kill $(lsof -ti :5050) && venv/bin/python app.py > /tmp/flask.log 2>&1 &`
- **Checkbox sync**: Keep all 4 frontend sections identical
- **Be proactive**: After finishing tasks, look for obvious improvements and make them
- **Update this file**: When making architectural changes, update CLAUDE.md immediately
