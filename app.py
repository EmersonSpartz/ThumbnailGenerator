"""
Thumbnail Generator - Flask Web App (v2)

Enhanced with:
1. Favorites system - Mark and learn from successful thumbnails
2. Variation generation - Click a thumbnail to generate more like it
3. Multiple image models - Gemini, Flux, SDXL, Ideogram
4. Improved prompting - Better thumbnail-specific prompts

Run with: python app.py
Then open: http://localhost:5050
"""

import os
import json
import time
import threading
import queue
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, Response, send_from_directory, send_file, jsonify

from lib import (
    Settings,
    ClaudeIdeator,
    MultiLLMIdeator,
    GeminiImageGenerator,
    ReplicateImageGenerator,
    IdeogramGenerator,
    MultiModelGenerator,
    FavoritesManager,
    FreshnessTracker,
    TextOverlay,
    ThumbnailRefiner,
    IterationSession,
    job_manager,
    PromptManager,
    AgenticImageRefiner,
    job_event_store,
)
from lib.claude_client import (
    get_last_prompt, get_last_response, get_last_thinking,
    get_current_thinking, get_current_response, reset_current_stream
)
from lib.logo_compositor import LogoCompositor
from lib.logo_stylizer import LogoStylizer

_logo_compositor = LogoCompositor()
_logo_stylizer = LogoStylizer()


def _apply_logos_to_image(file_path: str, titles: str = "", creative_direction: str = "", concept_name: str = ""):
    """Auto-detect and composite logos onto a generated thumbnail. Modifies file in place."""
    try:
        abs_path = str(settings.output_dir / file_path)
        _, logos_applied, placements = _logo_compositor.auto_composite(
            image_path=abs_path,
            title=titles,
            creative_direction=creative_direction,
            concept_name=concept_name,
            output_path=abs_path,
        )
        if logos_applied:
            print(f"[LOGO] Applied {logos_applied} to {file_path}")

            # Check for stylization instructions in creative direction
            logo_styles = _logo_compositor.detect_logo_styles(creative_direction)
            if logo_styles and placements and _logo_stylizer.available:
                from PIL import Image as PILImage
                img = PILImage.open(abs_path)
                stylized = _logo_stylizer.stylize_logos(
                    abs_path, placements, logo_styles, img.size
                )
                if stylized:
                    print(f"[LOGO-STYLE] Stylized {stylized} on {file_path}")
    except Exception as le:
        print(f"[LOGO] Failed for {file_path}: {le}")

from functools import wraps

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
settings = Settings()

# Global stop flag
_stop_generation = False

# Simple password auth (only enforced in production)
APP_PASSWORD = os.getenv('APP_PASSWORD', '')

def require_auth(f):
    """Simple password auth for production deployment."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not APP_PASSWORD:
            return f(*args, **kwargs)  # No auth in local dev
        # Check session cookie
        from flask import session
        if session.get('authenticated'):
            return f(*args, **kwargs)
        # Check query param (for SSE endpoints)
        if request.args.get('auth') == APP_PASSWORD:
            return f(*args, **kwargs)
        # Show login form
        if request.method == 'POST' and request.form.get('password') == APP_PASSWORD:
            session['authenticated'] = True
            return f(*args, **kwargs)
        return '''
        <html><body style="background:#111;color:#fff;font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
        <form method="post" style="text-align:center;">
            <h2>Thumbnail Generator</h2>
            <input type="password" name="password" placeholder="Password" autofocus
                   style="padding:12px;font-size:16px;border-radius:8px;border:1px solid #444;background:#222;color:#fff;margin:10px;">
            <br><button type="submit" style="padding:12px 24px;font-size:16px;border-radius:8px;border:none;background:#ff0000;color:#fff;cursor:pointer;">Enter</button>
        </form></body></html>
        ''', 401
    return decorated

@app.before_request
def check_auth_api():
    """Protect all /api/ routes with auth."""
    if not APP_PASSWORD:
        return  # No auth in local dev
    if request.path == '/health':
        return  # Health check bypasses auth
    if not request.path.startswith('/api/') and not request.path.startswith('/output/'):
        return  # Only protect API and output routes (main page has its own auth)
    from flask import session
    if session.get('authenticated'):
        return
    if request.args.get('auth') == APP_PASSWORD:
        return
    return jsonify({'error': 'Unauthorized'}), 401


@app.route('/health')
def health():
    """Health check endpoint for Railway (no auth required).
    Also runs auto-cleanup to prevent disk-full crashes.
    Always returns 200 so Railway doesn't kill the container — disk issues
    are logged but don't block the health check.
    """
    import shutil

    # Auto-cleanup on every health check (runs every ~30s on Railway)
    _auto_cleanup_if_needed()

    # Check disk space - cleanup old folders but NEVER delete recent work
    try:
        usage = shutil.disk_usage(str(settings.output_dir))
        free_mb = usage.free / (1024 * 1024)
        if free_mb < 200:
            _auto_cleanup_if_needed(max_folders=5, min_age_hours=6)
            usage = shutil.disk_usage(str(settings.output_dir))
            free_mb = usage.free / (1024 * 1024)
            if free_mb < 100:
                _auto_cleanup_if_needed(max_folders=2, min_age_hours=2)
                _deep_cleanup()
                usage = shutil.disk_usage(str(settings.output_dir))
                free_mb = usage.free / (1024 * 1024)
            if free_mb < 50:
                # Critical: delete everything except 1 folder, no age limit
                _auto_cleanup_if_needed(max_folders=1, min_age_hours=0)
                usage = shutil.disk_usage(str(settings.output_dir))
                free_mb = usage.free / (1024 * 1024)
            if free_mb < 200:
                print(f"[HEALTH] Disk low: {free_mb:.0f}MB free after cleanup")
            return jsonify({'status': 'ok', 'free_mb': round(free_mb)})
    except Exception:
        pass

    return jsonify({'status': 'ok'})


@app.route('/api/cleanup', methods=['POST'])
def force_cleanup():
    """Force aggressive disk cleanup.
    Favorites are already copied to data/favorites_images/, so output folders
    are all safe to delete. Keeps only the 2 most recent output folders.
    """
    import shutil
    # All output folders are safe to delete — favorites already backed up to data/favorites_images/
    _auto_cleanup_if_needed(max_folders=2, min_age_hours=0, ignore_protected=True)
    _deep_cleanup()
    try:
        usage = shutil.disk_usage(str(settings.output_dir))
        free_mb = usage.free / (1024 * 1024)
        return jsonify({'status': 'ok', 'free_mb': round(free_mb)})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/api/disk-usage')
def disk_usage():
    """Show disk usage breakdown by directory."""
    import shutil, subprocess
    result = {}
    persistent = settings.data_dir.parent  # /app/persistent
    try:
        usage = shutil.disk_usage(str(persistent))
        result['total_mb'] = round(usage.total / 1024 / 1024)
        result['used_mb'] = round(usage.used / 1024 / 1024)
        result['free_mb'] = round(usage.free / 1024 / 1024)
    except Exception as e:
        result['disk_error'] = str(e)
    # du on key dirs
    dirs_to_check = [settings.output_dir, settings.data_dir]
    breakdown = {}
    for d in dirs_to_check:
        if d.exists():
            try:
                out = subprocess.check_output(['du', '-sm', str(d)], text=True)
                mb = int(out.split()[0])
                breakdown[str(d)] = mb
                # Also list subdirs > 10MB
                subdirs = {}
                for sub in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)[:20]:
                    if sub.is_dir():
                        try:
                            out2 = subprocess.check_output(['du', '-sm', str(sub)], text=True)
                            smb = int(out2.split()[0])
                            if smb > 5:
                                subdirs[sub.name] = smb
                        except Exception:
                            pass
                if subdirs:
                    breakdown[str(d) + '_subdirs'] = subdirs
            except Exception as e:
                breakdown[str(d)] = str(e)
    result['breakdown'] = breakdown
    return jsonify(result)



def sse_message(data: dict) -> str:
    """Format a dict as an SSE message."""
    return f"data: {json.dumps(data)}\n\n"


def sse_keepalive() -> str:
    """Send an SSE keepalive data event to prevent proxy timeout."""
    return 'data: {"type":"keepalive"}\n\n'


def sse_response(stream):
    """Create an SSE Response with headers that prevent Railway/Nginx buffering."""
    resp = Response(stream, mimetype='text/event-stream')
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Connection'] = 'keep-alive'
    return resp


@app.route('/', methods=['GET', 'POST'])
@require_auth
def index():
    """Serve the main web UI."""
    return render_template('index.html')


@app.route('/output/<path:filename>')
def serve_output(filename):
    """Serve generated thumbnail images."""
    return send_from_directory(settings.output_dir, filename)


@app.route('/data/<path:filename>')
def serve_data(filename):
    """Serve protected files (favorites images, etc.)."""
    return send_from_directory(settings.data_dir, filename)


def _get_species_style():
    """Get the Species post-processing preset from the request."""
    return request.args.get('species_style', 'none')


def _make_generator():
    """Create a MultiModelGenerator with Species post-processing if requested."""
    return MultiModelGenerator(settings, post_process=_get_species_style())


@app.route('/api/health')
def health_check():
    """Basic health check endpoint."""
    return jsonify({"status": "ok"})


@app.route('/api/species-preview')
def species_preview():
    """Preview Species post-processing on an existing image. Pass ?path=output/...&preset=subtle"""
    from lib.species_post_processor import SpeciesPostProcessor
    from PIL import Image as PILImage
    import io

    image_path = request.args.get('path', '')
    preset = request.args.get('preset', 'subtle')

    if not image_path:
        return jsonify({"error": "No path provided"}), 400

    # Resolve relative to output dir or absolute
    full_path = Path(image_path)
    if not full_path.is_absolute():
        full_path = settings.output_dir / image_path

    if not full_path.exists():
        return jsonify({"error": f"File not found: {image_path}"}), 404

    processor = SpeciesPostProcessor(preset)
    img = PILImage.open(full_path).convert("RGB")
    processed = processor.process(img)

    buf = io.BytesIO()
    ext = full_path.suffix.lower()
    if ext in ('.jpg', '.jpeg'):
        processed.save(buf, 'JPEG', quality=95)
        mimetype = 'image/jpeg'
    else:
        processed.save(buf, 'PNG')
        mimetype = 'image/png'
    buf.seek(0)

    return send_file(buf, mimetype=mimetype)


@app.route('/api/species-presets')
def species_presets():
    """Get available Species post-processing presets."""
    from lib.species_post_processor import SpeciesPostProcessor
    return jsonify({
        "presets": list(SpeciesPostProcessor.PRESETS.keys()),
        "default": "subtle"
    })


@app.route('/api/models')
def get_available_models():
    """Get list of available image generation models."""
    multi_gen = _make_generator()
    models = multi_gen.get_available_models()

    # Add model info
    model_info = {
        "nanobanana2": {"name": "NanoBanana 2 Pro", "description": "Pro quality at Flash speed - Google's best image model"},
        "flux": {"name": "Flux Schnell", "description": "Fast, high-quality images with good composition"},
        "sdxl": {"name": "SDXL Lightning", "description": "Stability AI model, very fast"},
        "ideogram": {"name": "Ideogram", "description": "Best for text in images - great for thumbnails with titles"},
        "aispecies": {"name": "AI Species", "description": "Custom model trained on your channel's thumbnails"},
        "midjourney": {"name": "Midjourney", "description": "High-quality artistic images via LegNext.ai"},
        "recraft": {"name": "Recraft V3", "description": "Design-quality images, clean premium aesthetic"},
    }

    return jsonify({
        "models": [{"id": m, **model_info.get(m, {"name": m, "description": ""})} for m in models]
    })


# ============================================================
# FAVORITES SYSTEM (Feature #1)
# ============================================================

@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    """Get all favorite thumbnails, optionally filtered by video."""
    favorites_mgr = FavoritesManager(settings)
    video_name = request.args.get('video', None)
    all_favs = favorites_mgr.get_all_favorites()
    if video_name:
        all_favs = [f for f in all_favs if f.get("video_name") == video_name]
    return jsonify({
        "favorites": all_favs,
        "patterns": favorites_mgr.get_success_patterns()
    })


@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """Add a thumbnail to favorites."""
    data = request.json
    if not data or not data.get('thumbnail_path'):
        return jsonify({"success": False, "error": "thumbnail_path is required"}), 400

    favorites_mgr = FavoritesManager(settings)

    favorite = favorites_mgr.add_favorite(
        thumbnail_path=data.get('thumbnail_path', ''),
        concept_name=data.get('concept_name', ''),
        prompt=data.get('prompt', ''),
        title_ref=data.get('title_ref', ''),
        category=data.get('category', ''),
        description=data.get('description', ''),
        notes=data.get('notes', ''),
        performance_data=data.get('performance_data'),
        video_name=data.get('video_name', ''),
        thumbnail_text=data.get('thumbnail_text', ''),
        original_file_path=data.get('original_file_path', ''),
        model=data.get('model', ''),
        gen_title=data.get('gen_title', ''),
    )

    return jsonify({"success": True, "favorite": favorite})


@app.route('/api/favorites/<int:favorite_id>', methods=['DELETE'])
def remove_favorite(favorite_id):
    """Remove a thumbnail from favorites."""
    favorites_mgr = FavoritesManager(settings)
    success = favorites_mgr.remove_favorite(favorite_id)
    return jsonify({"success": success})


# ============================================================
# HISTORY API
# ============================================================

@app.route('/api/history')
def get_history():
    """Get thumbnail generation history, optionally filtered by video."""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    video_name = request.args.get('video', None)
    return jsonify(job_manager.get_history(limit=limit, offset=offset, video_name=video_name))


@app.route('/api/videos')
def get_videos():
    """Get all known video names."""
    return jsonify({"videos": job_manager.get_all_video_names()})


@app.route('/api/last-shootout')
def get_last_shootout():
    """Get the last model shootout results grouped by concept."""
    history = job_manager.get_history(limit=200, offset=0)
    thumbnails = history.get('thumbnails', [])

    # Find all thumbnails from the most recent shootout batch
    shootout_batches = {}
    for thumb in thumbnails:
        batch_id = thumb.get('batch_id', '')
        if 'shootout' in batch_id:
            if batch_id not in shootout_batches:
                shootout_batches[batch_id] = []
            shootout_batches[batch_id].append(thumb)

    if not shootout_batches:
        return jsonify({"success": False, "message": "No shootout history found"})

    # Get the most recent batch (sorted by batch_id which includes timestamp)
    latest_batch_id = sorted(shootout_batches.keys(), reverse=True)[0]
    batch_thumbnails = shootout_batches[latest_batch_id]

    # Group by concept
    concepts = {}
    for thumb in batch_thumbnails:
        concept_name = thumb.get('concept_name', 'Unknown')
        if concept_name not in concepts:
            concepts[concept_name] = {
                'concept_name': concept_name,
                'description': thumb.get('description', ''),
                'category': thumb.get('category', ''),
                'title_ref': thumb.get('title_ref', ''),
                'models': {}
            }
        concepts[concept_name]['models'][thumb.get('model', 'unknown')] = {
            'file_path': thumb.get('file_path', ''),
            'prompt': thumb.get('prompt', '')
        }

    return jsonify({
        "success": True,
        "batch_id": latest_batch_id,
        "concepts": list(concepts.values())
    })


# ============================================================
# DEBUG / TRANSPARENCY API
# ============================================================

@app.route('/api/debug-log')
def get_debug_log():
    """
    Get the last Claude prompt, response, and thinking for debugging.
    Provides transparency into what Claude received and how it processed it.
    """
    return jsonify({
        "prompt": get_last_prompt(),
        "thinking": get_last_thinking(),
        "response": get_last_response(),
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/live-stream')
def get_live_stream():
    """
    Get the current streaming state - what Claude is thinking/writing RIGHT NOW.
    Poll this endpoint to get real-time updates during generation.
    """
    return jsonify({
        "thinking": get_current_thinking(),
        "response": get_current_response(),
        "prompt": get_last_prompt(),
        "timestamp": datetime.now().isoformat()
    })


# ============================================================
# PROMPT MANAGEMENT - Editable prompts with versioning
# ============================================================

# Initialize prompt manager
prompt_manager = PromptManager(settings.data_dir)


@app.route('/api/prompts')
def get_prompts():
    """Get all editable prompts."""
    return jsonify({
        "prompts": prompt_manager.get_all_prompts(),
        "history": prompt_manager.get_history(limit=10)
    })


@app.route('/api/rubric')
def get_rubric_alias():
    """Alias for /api/get-rubric for consistency."""
    return get_rubric()


@app.route('/api/prompts/<key>', methods=['GET'])
def get_prompt(key):
    """Get a specific prompt by key."""
    value = prompt_manager.get_prompt(key)
    if not value:
        return jsonify({"error": f"Prompt key '{key}' not found"}), 404
    return jsonify({
        "key": key,
        "value": value
    })


@app.route('/api/prompts/<key>', methods=['POST'])
def update_prompt(key):
    """
    Update a prompt.
    POST body: { "value": "new prompt text", "note": "optional change note" }
    """
    data = request.json
    new_value = data.get('value', '')
    note = data.get('note', '')

    change_record = prompt_manager.update_prompt(key, new_value, note)

    return jsonify({
        "success": True,
        "change": change_record
    })


@app.route('/api/prompts/history')
def get_prompt_history():
    """Get prompt change history."""
    limit = request.args.get('limit', 20, type=int)
    return jsonify({
        "history": prompt_manager.get_history(limit=limit)
    })


@app.route('/api/prompts/rollback', methods=['POST'])
def rollback_prompt():
    """
    Rollback a prompt to a previous version.
    POST body: { "timestamp": "ISO timestamp of the change to undo" }
    """
    data = request.json
    timestamp = data.get('timestamp', '')

    success = prompt_manager.rollback(timestamp)

    return jsonify({
        "success": success,
        "message": "Rolled back successfully" if success else "Rollback failed - timestamp not found"
    })


@app.route('/api/prompts/preview', methods=['POST'])
def preview_prompt():
    """
    Preview the full prompt that would be sent to Claude.
    POST body: { "titles": ["title1", "title2"], "script": "", "creative_direction": "" }
    """
    data = request.json
    titles = data.get('titles', [])
    script = data.get('script', '')
    creative_direction = data.get('creative_direction', '')

    full_prompt = prompt_manager.build_full_prompt(titles, script, creative_direction)

    return jsonify({
        "prompt": full_prompt
    })


@app.route('/api/pipeline-debug')
def get_pipeline_debug():
    """
    Get a COMPREHENSIVE view of the entire generation pipeline.
    Shows the ACTUAL last prompts that were sent (not examples).
    """
    # Get the ACTUAL last prompt that was sent to Claude
    last_concept_prompt = get_last_prompt()

    # Stage 2: Image Prompt Template + Prompting Guide
    image_prompt_template = prompt_manager.get_prompt('image_prompt_template')
    prompting_guide = prompt_manager.get_prompt('prompting_guide')

    # Build the full image prompt instruction (what Claude sees when writing image prompts)
    ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
    sample_concepts = [
        {
            "concept_name": "Example Concept",
            "category": "Power Dynamic",
            "title_ref": "Example Video Title",
            "description": "A massive robot looming over a tiny human"
        }
    ]
    image_prompt_full = ideator._build_prompts_prompt(sample_concepts)

    # Stage 3: What actually goes to image models
    # This is the final prompt string that gets sent to Gemini/Flux/etc
    sample_image_prompt = "Cinematic wide shot of massive metallic robot towering over tiny human silhouette, dramatic red and blue lighting, apocalyptic sky, extreme scale contrast showing robot 100x taller than human, bold graphic style, 16:9 YouTube thumbnail, high contrast"

    # Get available models
    multi_gen = _make_generator()
    available_models = multi_gen.get_available_models()

    return jsonify({
        "stage_1_concept_generation": {
            "description": "This is sent to Claude to generate thumbnail CONCEPTS (ideas, not images yet)",
            "prompt": last_concept_prompt if last_concept_prompt else "(No generation run yet - run a generation first to see the actual prompt)",
            "placeholders_used": ["{{TITLES}}", "{{COUNT}}", "{{SCRIPT_SECTION}}", "{{CREATIVE_DIRECTION_SECTION}}"]
        },
        "stage_2_image_prompt_writing": {
            "description": "After concepts are generated, this is sent to Claude to write IMAGE PROMPTS for each concept",
            "template_instruction": image_prompt_template,
            "prompting_guide": prompting_guide,
            "full_prompt_example": image_prompt_full
        },
        "stage_3_image_generation": {
            "description": "The final prompt string that gets sent directly to each image model (Gemini, Flux, etc)",
            "example_prompt": sample_image_prompt,
            "models_available": available_models,
            "note": "Each model receives the SAME prompt - they interpret it differently based on their training"
        },
        "last_actual_prompts": {
            "last_concept_prompt": get_last_prompt(),
            "last_claude_response": get_last_response()[:2000] if get_last_response() else None
        }
    })


# ============================================================
# VARIATION GENERATION (Feature #2)
# ============================================================

@app.route('/api/variations')
def generate_variations():
    """
    Generate variations of a favorite/selected thumbnail.

    Query params:
    - favorite_id: ID of the favorite to base variations on
    - num_variations: How many to generate (default 5)
    - style: "similar", "explore", or "remix"
    - model: Which image model to use
    """
    favorite_id = int(request.args.get('favorite_id', 0))
    num_variations = int(request.args.get('num_variations', 5))
    variation_style = request.args.get('style', 'similar')
    model_key = request.args.get('model', 'gemini')

    favorites_mgr = FavoritesManager(settings)
    base_concept = favorites_mgr.get_favorite_for_variation(favorite_id)

    if not base_concept:
        return Response(
            sse_message({'type': 'error', 'message': 'Favorite not found'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        # Initialize components (pass prompt_manager so edits take effect)
        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()

        yield sse_message({
            'type': 'progress',
            'message': f'Generating {num_variations} variations of "{base_concept["concept_name"]}"...'
        })

        # Step 1: Generate variation concepts with Claude
        try:
            concepts = ideator.generate_variations(
                base_concept=base_concept,
                num_variations=num_variations,
                variation_style=variation_style
            )
            yield sse_message({
                'type': 'progress',
                'message': f'Generated {len(concepts)} variation concepts'
            })
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
            return

        if not concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated'})
            return

        # Step 2: Generate prompts for variations
        try:
            prompts_with_concepts = ideator.generate_prompts_for_concepts(concepts)
            yield sse_message({
                'type': 'progress',
                'message': f'Generated prompts for {len(prompts_with_concepts)} concepts'
            })
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Prompt generation error: {str(e)}'})
            return

        # Step 3: Generate images
        generated = 0
        for prompt_data in prompts_with_concepts:
            if _stop_generation:
                yield sse_message({'type': 'stopped', 'message': 'Generation stopped', 'total': generated})
                return

            # Retry logic for rate limiting
            max_retries = 3
            for retry in range(max_retries):
                result = generator.generate_with_model(model_key, prompt_data, "variations")

                if result.get('success'):
                    generated += 1
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                    yield sse_message({
                        'type': 'thumbnail',
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': prompt_data.get('description', ''),
                        'based_on': base_concept['concept_name'],
                        'prompt': prompt_data.get('prompt', ''),
                        'category': prompt_data.get('category', ''),
                    })
                    break
                elif '429' in str(result.get('error', '')) or 'rate' in str(result.get('error', '')).lower():
                    # Rate limited - wait and retry
                    if retry < max_retries - 1:
                        yield sse_message({
                            'type': 'progress',
                            'message': f'Rate limited, waiting 3 seconds before retry ({retry + 1}/{max_retries})...'
                        })
                        time.sleep(3)
                    else:
                        yield sse_message({
                            'type': 'error',
                            'message': f'Rate limit exceeded after {max_retries} retries. Try using Gemini (free) or wait a minute.'
                        })
                else:
                    yield sse_message({
                        'type': 'error',
                        'message': f'Generation failed: {result.get("error", "Unknown")}'
                    })
                    break

            time.sleep(1)  # Increased delay between generations

        yield sse_message({
            'type': 'complete',
            'total': generated,
            'message': f'Generated {generated} variations'
        })

    return sse_response(generate_stream())


@app.route('/api/quick-variations')
def quick_variations():
    """
    Generate variations by re-rendering the SAME prompt multiple times.
    No Claude involvement - just let the image models take more cracks at it.

    Query params:
    - favorite_id: ID of the favorite to base variations on (optional)
    - prompt: Direct prompt to use (optional, used if no favorite_id)
    - num_variations: How many to generate per model
    - models: Comma-separated list of models to use
    """
    favorite_id = request.args.get('favorite_id', '')
    direct_prompt = request.args.get('prompt', '')
    num_variations = int(request.args.get('num_variations', 5))
    models_str = request.args.get('models', 'nanobanana2')
    thumbnail_text = request.args.get('thumbnail_text', '')
    video_name = request.args.get('video_name', '')

    selected_models = [m.strip() for m in models_str.split(',') if m.strip()]

    # Get prompt either from favorite or directly
    original_prompt = ''
    concept_name = 'Quick Variation'

    if favorite_id and favorite_id != '0':
        favorites_mgr = FavoritesManager(settings)
        base_concept = favorites_mgr.get_favorite_for_variation(int(favorite_id))
        if base_concept:
            original_prompt = base_concept.get('prompt', '')
            concept_name = base_concept.get('concept_name', 'Variation')
    elif direct_prompt:
        original_prompt = direct_prompt
        concept_name = 'Re-render'

    if not original_prompt:
        return Response(
            sse_message({'type': 'error', 'message': 'No prompt provided. Pass favorite_id or prompt parameter.'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        generator = _make_generator()
        available_models = generator.get_available_models()
        models_to_use = [m for m in selected_models if m in available_models]

        if not models_to_use:
            yield sse_message({'type': 'error', 'message': 'No valid models selected'})
            return

        total_images = num_variations * len(models_to_use)

        yield sse_message({
            'type': 'parallel_start',
            'models': models_to_use,
            'total_models': len(models_to_use),
            'concepts_per_model': num_variations,
            'total': total_images,
            'message': f'Quick variations: {num_variations} renders × {len(models_to_use)} models = {total_images} images'
        })

        # Initialize model status
        for model in models_to_use:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'Starting...',
                'progress': 0,
                'total': num_variations
            })

        completed_per_model = {m: 0 for m in models_to_use}
        total_completed = 0
        batch_id = f"quick_var_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def generate_one(model_name, variation_num):
            """Generate a single image with the same prompt."""
            prompt_data = {
                'prompt': original_prompt,
                'concept_name': f"{concept_name}_{variation_num + 1}",
            }
            result = generator.generate_with_model(model_name, prompt_data, f"{batch_id}/{model_name}")
            return model_name, prompt_data, result, variation_num

        # Create all tasks
        tasks = []
        for var_num in range(num_variations):
            for model in models_to_use:
                tasks.append((model, var_num))

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            futures = [executor.submit(generate_one, m, v) for m, v in tasks]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Generation stopped'})
                    return

                try:
                    model_name, prompt_data, result, var_num = future.result()
                except Exception as e:
                    print(f"[VARIATIONS] Future failed: {e}")
                    continue
                completed_per_model[model_name] += 1
                total_completed += 1

                if result.get('success'):
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')

                    # Apply text overlay if thumbnail_text was provided
                    original_file_path = ''
                    if thumbnail_text:
                        try:
                            overlay = TextOverlay()
                            full_img_path = str(settings.output_dir / file_path)
                            output_path = overlay.add_text(
                                image_path=full_img_path,
                                text=thumbnail_text,
                                position='bottom-center',
                                style='impact',
                            )
                            original_file_path = file_path
                            file_path = str(Path(output_path).relative_to(settings.output_dir))
                        except Exception as e:
                            print(f"[VARIATIONS] Text overlay failed: {e}")

                    thumbnail_data = {
                        'type': 'model_thumbnail',
                        'model': model_name,
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': f"Re-render #{var_num + 1}",
                        'based_on': concept_name,
                        'prompt': original_prompt,
                        'thumbnail_text': thumbnail_text,
                        'original_file_path': original_file_path,
                        'current': completed_per_model[model_name],
                        'total': num_variations,
                        'overall_current': total_completed,
                        'overall_total': total_images,
                        'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                        'video_name': video_name,
                    }

                    # Save to history
                    job_manager.add_result(batch_id, thumbnail_data)

                    yield sse_message(thumbnail_data)

                    yield sse_message({
                        'type': 'model_progress',
                        'model': model_name,
                        'current': completed_per_model[model_name],
                        'total': num_variations
                    })
                else:
                    yield sse_message({
                        'type': 'model_error',
                        'model': model_name,
                        'error': result.get('error', 'Unknown')[:100]
                    })

        # Mark models complete
        for model in models_to_use:
            yield sse_message({
                'type': 'model_complete',
                'model': model,
                'count': completed_per_model[model]
            })

        yield sse_message({
            'type': 'parallel_complete',
            'total_generated': total_completed,
            'models': models_to_use,
            'message': f'Generated {total_completed} quick variations'
        })

    return sse_response(generate_stream())


@app.route('/api/parallel-variations')
def parallel_variations_get():
    """
    Generate Claude variations using multiple models IN PARALLEL (GET version for SSE).

    Query params:
    - favorite_id: ID of the favorite to base variations on
    - num_variations: How many variations
    - style: "similar", "explore", or "remix"
    - models: Comma-separated list of models to use
    """
    favorite_id = int(request.args.get('favorite_id', 0))
    num_variations = int(request.args.get('num_variations', 5))
    variation_style = request.args.get('style', 'similar')
    models_str = request.args.get('models', 'nanobanana2')

    selected_models = [m.strip() for m in models_str.split(',') if m.strip()]

    favorites_mgr = FavoritesManager(settings)
    base_concept = favorites_mgr.get_favorite_for_variation(favorite_id)

    if not base_concept:
        return Response(
            sse_message({'type': 'error', 'message': 'Favorite not found'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()
        available_models = generator.get_available_models()

        models_to_use = [m for m in selected_models if m in available_models]

        if not models_to_use:
            yield sse_message({'type': 'error', 'message': 'No valid models selected'})
            return

        yield sse_message({
            'type': 'progress',
            'message': f'Claude is generating {num_variations} variation concepts...'
        })

        # Generate variation concepts with Claude
        try:
            concepts = ideator.generate_variations(
                base_concept=base_concept,
                num_variations=num_variations,
                variation_style=variation_style
            )
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
            return

        if not concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated'})
            return

        yield sse_message({
            'type': 'progress',
            'message': f'Generating prompts for {len(concepts)} concepts...'
        })

        try:
            prompts_with_concepts = ideator.generate_prompts_for_concepts(concepts)
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Prompt error: {str(e)}'})
            return

        # Parallel image generation
        total_images = len(prompts_with_concepts) * len(models_to_use)

        yield sse_message({
            'type': 'parallel_start',
            'models': models_to_use,
            'total_models': len(models_to_use),
            'concepts_per_model': len(prompts_with_concepts),
            'total': total_images,
            'message': f'Generating {total_images} images ({len(prompts_with_concepts)} concepts × {len(models_to_use)} models)...'
        })

        for model in models_to_use:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'Starting...',
                'progress': 0,
                'total': len(prompts_with_concepts)
            })

        completed_per_model = {m: 0 for m in models_to_use}
        total_completed = 0
        batch_id = f"par_var_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def generate_one(model_name, prompt_data, idx):
            result = generator.generate_with_model(model_name, prompt_data, f"{batch_id}/{model_name}")
            return model_name, prompt_data, result, idx

        tasks = []
        for idx, prompt_data in enumerate(prompts_with_concepts):
            for model in models_to_use:
                tasks.append((model, prompt_data, idx))

        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            futures = [executor.submit(generate_one, m, p, i) for m, p, i in tasks]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Generation stopped'})
                    return

                try:
                    model_name, prompt_data, result, idx = future.result()
                except Exception as e:
                    print(f"[QUICK-VAR] Future failed: {e}")
                    continue
                completed_per_model[model_name] += 1
                total_completed += 1

                if result.get('success'):
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')

                    yield sse_message({
                        'type': 'model_thumbnail',
                        'model': model_name,
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': prompt_data.get('description', ''),
                        'based_on': base_concept.get('concept_name', ''),
                        'prompt': prompt_data.get('prompt', ''),
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts),
                        'overall_current': total_completed,
                        'overall_total': total_images,
                        'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                    })

                    yield sse_message({
                        'type': 'model_progress',
                        'model': model_name,
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts)
                    })
                else:
                    yield sse_message({
                        'type': 'model_error',
                        'model': model_name,
                        'error': result.get('error', 'Unknown')[:100]
                    })

        for model in models_to_use:
            yield sse_message({
                'type': 'model_complete',
                'model': model,
                'count': completed_per_model[model]
            })

        yield sse_message({
            'type': 'parallel_complete',
            'total_generated': total_completed,
            'models': models_to_use,
            'message': f'Generated {total_completed} variations across {len(models_to_use)} models'
        })

    return sse_response(generate_stream())


# ============================================================
# MAIN GENERATION (Enhanced)
# ============================================================

@app.route('/generate')
def generate():
    """
    Generate thumbnails via Server-Sent Events.

    Query params:
    - titles: Newline-separated video titles
    - script: Optional video script for context
    - creative_direction: Optional guidance for visual style (e.g., "fungal body horror")
    - count: Total thumbnails to generate (default 20)
    - batch_size: Ideas per batch (default 20)
    - model: Image model to use ('gemini', 'flux', 'sdxl', 'ideogram')
    - use_favorites: Whether to learn from favorites (default true)
    """
    titles_raw = request.args.get('titles', '')
    script = request.args.get('script', '')
    creative_direction = request.args.get('creative_direction', '')
    count = int(request.args.get('count', 20))
    batch_size = int(request.args.get('batch_size', 20))
    model_key = request.args.get('model', 'gemini')
    use_favorites = request.args.get('use_favorites', 'true').lower() == 'true'

    titles = [t.strip() for t in titles_raw.split('\n') if t.strip()]

    if not titles:
        return Response(
            sse_message({'type': 'error', 'message': 'No titles provided'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        # Initialize components (pass prompt_manager so edits take effect)
        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()
        freshness = FreshnessTracker(settings)
        favorites_mgr = FavoritesManager(settings)

        # Get favorites context if enabled (NEW FEATURE)
        favorites_context = ""
        if use_favorites:
            favorites_context = favorites_mgr.get_favorites_summary_for_prompt(limit=5)
            if favorites_context:
                yield sse_message({
                    'type': 'progress',
                    'message': 'Using favorites to guide generation...'
                })

        total_batches = (count + batch_size - 1) // batch_size
        generated = 0
        batch_num = 0

        while generated < count and batch_num < total_batches:
            if _stop_generation:
                yield sse_message({'type': 'stopped', 'message': 'Generation stopped', 'total': generated})
                return

            batch_num += 1
            batch_id = f"batch_{batch_num:03d}"

            yield sse_message({
                'type': 'progress',
                'current': generated,
                'total': count,
                'message': f'Batch {batch_num}/{total_batches}: Generating ideas with Claude...'
            })

            # Check category balance
            stats = freshness.get_category_stats()
            category_hint = ""
            if stats.get('imbalanced'):
                underrep = freshness.get_underrepresented_categories()
                if underrep:
                    category_hint = f"Focus more on: {', '.join(underrep)}"

            # COMBINED: Generate concepts AND prompts in single Claude call (~2x faster)
            this_batch_count = min(batch_size, count - generated)
            try:
                prompts_with_concepts = []
                for event in ideator.generate_concepts_and_prompts_streaming(
                    titles=titles,
                    used_ideas=freshness.get_summary_list(),
                    batch_number=batch_num,
                    script=script,
                    favorites_context="",
                    category_hint=category_hint,
                    creative_direction=creative_direction,
                    count=this_batch_count
                ):
                    if event['type'] == 'prompt':
                        yield sse_message({
                            'type': 'claude_prompt',
                            'content': event['content']
                        })
                    elif event['type'] == 'thinking_start':
                        yield sse_message({
                            'type': 'claude_thinking_start'
                        })
                    elif event['type'] == 'thinking_delta':
                        yield sse_message({
                            'type': 'claude_thinking',
                            'content': event['content']
                        })
                    elif event['type'] == 'response_start':
                        yield sse_message({
                            'type': 'claude_response_start'
                        })
                    elif event['type'] == 'response_delta':
                        yield sse_message({
                            'type': 'claude_response',
                            'content': event['content']
                        })
                    elif event['type'] == 'complete':
                        yield sse_message({
                            'type': 'claude_complete'
                        })
                    elif event['type'] == 'prompts_ready':
                        prompts_with_concepts = event['prompts']

                yield sse_message({
                    'type': 'progress',
                    'current': generated,
                    'total': count,
                    'message': f'Batch {batch_num}: Got {len(prompts_with_concepts)} concepts+prompts from Claude'
                })
            except Exception as e:
                yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
                continue

            if not prompts_with_concepts:
                yield sse_message({'type': 'error', 'message': 'No concepts generated'})
                continue

            # Filter for freshness
            fresh_prompts = freshness.filter_fresh(prompts_with_concepts)
            yield sse_message({
                'type': 'progress',
                'current': generated,
                'total': count,
                'message': f'Batch {batch_num}: {len(fresh_prompts)}/{len(prompts_with_concepts)} concepts are fresh'
            })

            if not fresh_prompts:
                yield sse_message({
                    'type': 'progress',
                    'message': f'Batch {batch_num}: All concepts too similar, retrying...'
                })
                continue

            # Generate images IN PARALLEL for speed
            prompts_to_generate = [p for p in fresh_prompts if generated + fresh_prompts.index(p) < count]
            if _stop_generation:
                break

            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _gen_image(prompt_data):
                """Generate a single image with retry logic."""
                max_retries = 3
                for retry in range(max_retries):
                    result = generator.generate_with_model(model_key, prompt_data, batch_id)
                    if result.get('success'):
                        return {'success': True, 'result': result, 'prompt_data': prompt_data}
                    elif '429' in str(result.get('error', '')) or 'rate' in str(result.get('error', '')).lower():
                        if retry < max_retries - 1:
                            time.sleep(3 * (retry + 1))
                        else:
                            return {'success': False, 'error': 'Rate limit exceeded', 'prompt_data': prompt_data}
                    else:
                        return {'success': False, 'error': result.get('error', 'Unknown error'), 'prompt_data': prompt_data, 'quota_exhausted': result.get('quota_exhausted')}
                return {'success': False, 'error': 'Max retries exceeded', 'prompt_data': prompt_data}

            yield sse_message({
                'type': 'progress',
                'current': generated,
                'total': count,
                'message': f'Generating {len(prompts_to_generate)} images in parallel...'
            })

            with ThreadPoolExecutor(max_workers=min(len(prompts_to_generate), 5)) as img_executor:
                futures = {img_executor.submit(_gen_image, pd): pd for pd in prompts_to_generate}
                for future in as_completed(futures):
                    if _stop_generation:
                        break
                    try:
                        gen_result = future.result()
                    except Exception as e:
                        yield sse_message({'type': 'error', 'message': f'Image generation failed: {str(e)}'})
                        continue

                    if gen_result['success']:
                        result = gen_result['result']
                        prompt_data = gen_result['prompt_data']
                        freshness.add_used_idea(prompt_data)
                        generated += 1

                        file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                        yield sse_message({
                            'type': 'thumbnail',
                            'file_path': file_path,
                            'concept_name': prompt_data.get('concept_name', ''),
                            'title_ref': prompt_data.get('title_ref', ''),
                            'concept_summary': prompt_data.get('description', ''),
                            'category': prompt_data.get('category', ''),
                            'prompt': prompt_data.get('prompt', ''),
                        })

                        yield sse_message({
                            'type': 'progress',
                            'current': generated,
                            'total': count,
                            'message': f'Generated {generated}/{count}'
                        })
                    else:
                        error_msg = gen_result.get('error', 'Unknown error')
                        yield sse_message({'type': 'error', 'message': f'Image generation failed: {error_msg}'})

                        if gen_result.get('quota_exhausted'):
                            yield sse_message({
                                'type': 'quota_exhausted',
                                'message': 'All API keys exhausted. Add more keys or wait.'
                            })
                            return

        yield sse_message({
            'type': 'complete',
            'total': generated,
            'batches': batch_num,
            'message': f'Generation complete! Created {generated} thumbnails.'
        })

    return sse_response(generate_stream())


@app.route('/stop', methods=['POST'])
def stop_generation():
    """Stop ongoing generation."""
    global _stop_generation
    _stop_generation = True
    return jsonify({'status': 'ok', 'message': 'Stop signal sent'})


@app.route('/clear-history', methods=['POST'])
def clear_history():
    """Clear the used ideas history."""
    freshness = FreshnessTracker(settings)
    freshness.clear()
    return jsonify({'status': 'ok'})


def _get_protected_paths() -> set:
    """Get set of output folder names that contain favorited images — never delete these."""
    protected = set()
    try:
        favs = FavoritesManager(settings).get_all_favorites()
        for fav in favs:
            # original_output_path or thumbnail_path like "shootout_20260205/concept_1/flux/img.png"
            path = fav.get('original_output_path') or fav.get('thumbnail_path', '')
            if path and '/' in path:
                top_folder = path.split('/')[0]  # e.g. "shootout_20260205_131529"
                protected.add(top_folder)
    except Exception as e:
        print(f"[AUTO-CLEANUP] Warning: could not read favorites: {e}")
    return protected


def _deep_cleanup():
    """Clean __pycache__, temp files, and other non-essential disk usage."""
    import shutil
    app_dir = Path(__file__).parent
    # Clean __pycache__ directories
    for p in app_dir.rglob('__pycache__'):
        try:
            shutil.rmtree(p)
        except Exception:
            pass
    # Clean any .pyc files
    for p in app_dir.rglob('*.pyc'):
        try:
            p.unlink()
        except Exception:
            pass
    # Clean server.log if it exists
    log_file = app_dir / 'server.log'
    if log_file.exists() and log_file.stat().st_size > 1024 * 1024:
        try:
            log_file.write_text('')
        except Exception:
            pass


def _auto_cleanup_if_needed(max_folders=30, min_age_hours=24, ignore_protected=False):
    """Automatically clean old output when folder count exceeds threshold.
    ignore_protected=True: delete even folders with favorites (safe because
      favorites are already backed up to data/favorites_images/).
    """
    import shutil
    import time
    output_dir = settings.output_dir
    if not output_dir.exists():
        return
    folders = sorted(
        [f for f in output_dir.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime
    )
    if len(folders) <= max_folders:
        return
    protected = set() if ignore_protected else _get_protected_paths()
    now = time.time()
    age_cutoff = now - (min_age_hours * 3600)
    candidates = folders[:-max_folders]
    to_delete = [
        f for f in candidates
        if f.name not in protected and f.stat().st_mtime < age_cutoff
    ]
    skipped_protected = sum(1 for f in candidates if f.name in protected)
    skipped_young = sum(1 for f in candidates if f.name not in protected and f.stat().st_mtime >= age_cutoff)
    for folder in to_delete:
        try:
            shutil.rmtree(folder)
        except Exception:
            pass
    msg = f"[AUTO-CLEANUP] Deleted {len(to_delete)} old output folders, kept {max_folders}"
    if skipped_protected:
        msg += f", protected {skipped_protected} folders with favorites"
    if skipped_young:
        msg += f", kept {skipped_young} folders younger than {min_age_hours}h"
    print(msg)


def _protect_existing_favorites():
    """On startup, copy any unprotected favorite images to the protected directory."""
    import shutil as _shutil
    try:
        fav_mgr = FavoritesManager(settings)
        protected_dir = settings.data_dir / 'favorites_images'
        protected_dir.mkdir(parents=True, exist_ok=True)
        migrated = 0
        for fav in fav_mgr.get_all_favorites():
            # Skip already-protected favorites
            if fav.get('thumbnail_path', '').startswith('data/'):
                continue
            # Try to find the original in output dir
            orig_path = fav.get('original_output_path') or fav.get('thumbnail_path', '')
            src = settings.output_dir / orig_path
            if src.exists():
                ext = src.suffix
                dest = protected_dir / f"fav_{fav['id']}{ext}"
                if not dest.exists():
                    _shutil.copy2(str(src), str(dest))
                    migrated += 1
        if migrated:
            print(f"[FAVORITES] Startup migration: protected {migrated} existing favorite images")
    except Exception as e:
        print(f"[FAVORITES] Startup migration error: {e}")


@app.route('/api/cleanup-output', methods=['POST'])
def cleanup_output():
    """Delete old output folders to free disk space. Keeps the N most recent folders."""
    import shutil
    keep = request.args.get('keep', 10, type=int)

    output_dir = settings.output_dir
    if not output_dir.exists():
        return jsonify({'status': 'ok', 'message': 'No output directory'})

    # Get all subdirectories sorted by modification time (oldest first)
    folders = sorted(
        [f for f in output_dir.iterdir() if f.is_dir()],
        key=lambda f: f.stat().st_mtime
    )

    if len(folders) <= keep:
        return jsonify({'status': 'ok', 'message': f'Only {len(folders)} folders, nothing to clean', 'kept': len(folders)})

    protected = _get_protected_paths()
    candidates = folders[:-keep] if keep > 0 else folders
    to_delete = [f for f in candidates if f.name not in protected]
    skipped = len(candidates) - len(to_delete)
    deleted = 0
    freed_bytes = 0
    for folder in to_delete:
        try:
            size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
            shutil.rmtree(folder)
            deleted += 1
            freed_bytes += size
        except Exception as e:
            print(f"[CLEANUP] Error deleting {folder}: {e}")

    freed_mb = freed_bytes / (1024 * 1024)
    msg = f'Deleted {deleted} folders, freed ~{freed_mb:.0f} MB'
    if skipped:
        msg += f' (protected {skipped} folders with favorites)'
    return jsonify({
        'status': 'ok',
        'deleted_folders': deleted,
        'kept_folders': keep,
        'protected_folders': skipped,
        'freed_mb': round(freed_mb, 1),
        'message': msg
    })


def _require_video_name():
    """Check that video_name is provided. Returns error Response if missing, None if OK."""
    video_name = request.args.get('video_name', '').strip()
    if not video_name:
        def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'message': 'No video selected. Please select or create a video before generating.'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')
    return None


# ============================================================
# MODEL SHOOTOUT - Side-by-side comparison for each concept
# ============================================================

@app.route('/api/model-shootout')
def model_shootout():
    """
    Generate concepts with Claude, then render EACH concept with ALL models side-by-side.
    This helps you see which models perform best so you can eliminate weak ones.

    Returns results grouped by concept, with all model versions for easy comparison.

    Query params:
    - titles: Newline-separated video titles
    - script: Optional video script
    - creative_direction: Optional style guidance
    - count: Number of concepts (default 5 for comparison)
    - models: Comma-separated list of models (default: all)
    """
    err = _require_video_name()
    if err: return err
    titles_raw = request.args.get('titles', '')
    script = request.args.get('script', '')
    creative_direction = request.args.get('creative_direction', '')
    video_name = request.args.get('video_name', '')
    count = int(request.args.get('count', 5))  # Fewer concepts for easier comparison
    models_str = request.args.get('models', 'nanobanana2')

    selected_models = [m.strip() for m in models_str.split(',') if m.strip()]
    titles = [t.strip() for t in titles_raw.split('\n') if t.strip()]

    if not titles:
        return Response(
            sse_message({'type': 'error', 'message': 'No titles provided'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()

        available_models = generator.get_available_models()
        models_to_use = [m for m in selected_models if m in available_models]

        if not models_to_use:
            yield sse_message({'type': 'error', 'message': 'No valid models available'})
            return

        yield sse_message({
            'type': 'shootout_start',
            'models': models_to_use,
            'message': f'Model Shootout: {count} concepts × {len(models_to_use)} models'
        })

        # STEP 1: Generate concepts with Claude (thread+queue for Railway keepalive)
        concepts_queue = queue.Queue()

        def _stream_concepts():
            try:
                for event in ideator.generate_concepts_streaming(
                    titles=titles,
                    used_ideas=[],
                    batch_number=1,
                    script=script,
                    creative_direction=creative_direction,
                    count=count
                ):
                    concepts_queue.put(event)
            except Exception as e:
                concepts_queue.put({'type': 'error', 'error': str(e)})
            finally:
                concepts_queue.put(None)

        threading.Thread(target=_stream_concepts, daemon=True).start()

        concepts = []
        while True:
            try:
                event = concepts_queue.get(timeout=120)
            except queue.Empty:
                yield sse_message({'type': 'error', 'message': 'Concept generation timed out'})
                return
            if event is None:
                break
            if event['type'] == 'prompt':
                yield sse_message({'type': 'claude_prompt', 'content': event['content']})
            elif event['type'] == 'thinking_delta':
                yield sse_message({'type': 'claude_thinking', 'content': event['content']})
            elif event['type'] == 'response_delta':
                yield sse_message({'type': 'claude_response', 'content': event['content']})
            elif event['type'] == 'concepts':
                concepts = event['concepts']
            elif event['type'] == 'error':
                yield sse_message({'type': 'error', 'message': event['error']})
                return

        if not concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated'})
            return

        # Limit to requested count
        concepts = concepts[:count]

        yield sse_message({
            'type': 'concepts_ready',
            'count': len(concepts),
            'message': f'Got {len(concepts)} concepts, generating prompts...'
        })

        # STEP 2: Generate prompts (streaming so Railway doesn't timeout)
        prompts_queue = queue.Queue()

        def _stream_prompts():
            try:
                for event in ideator.generate_prompts_for_concepts_streaming(concepts):
                    prompts_queue.put(event)
            except Exception as e:
                prompts_queue.put({'type': 'error', 'error': str(e)})
            finally:
                prompts_queue.put(None)

        threading.Thread(target=_stream_prompts, daemon=True).start()

        prompts_with_concepts = []
        while True:
            try:
                event = prompts_queue.get(timeout=120)
            except queue.Empty:
                yield sse_message({'type': 'error', 'message': 'Prompt generation timed out'})
                return
            if event is None:
                break
            if event['type'] == 'prompt':
                yield sse_message({'type': 'claude_prompt', 'content': event['content']})
            elif event['type'] == 'thinking_delta':
                yield sse_message({'type': 'claude_thinking', 'content': event['content']})
            elif event['type'] == 'response_delta':
                yield sse_message({'type': 'claude_response', 'content': event['content']})
            elif event['type'] == 'prompts':
                prompts_with_concepts = event['prompts']
            elif event['type'] == 'error':
                yield sse_message({'type': 'error', 'message': event['error']})
                return
            else:
                yield sse_message({'type': 'keepalive'})

        yield sse_message({
            'type': 'prompts_ready',
            'count': len(prompts_with_concepts),
            'message': f'Ready to render {len(prompts_with_concepts)} concepts across {len(models_to_use)} models'
        })

        # STEP 3: For EACH concept, generate with ALL models (grouped output)
        batch_id = f"shootout_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create a job for history tracking
        job_id = job_manager.create_job('shootout', {
            'titles': titles,
            'creative_direction': creative_direction,
            'models': models_to_use,
            'count': count,
            'video_name': video_name,
        })
        job_manager.start_job(job_id)

        for concept_idx, prompt_data in enumerate(prompts_with_concepts):
            if _stop_generation:
                yield sse_message({'type': 'stopped', 'message': 'Stopped'})
                return

            concept_name = prompt_data.get('concept_name', f'Concept {concept_idx + 1}')

            yield sse_message({
                'type': 'concept_start',
                'concept_index': concept_idx,
                'concept_name': concept_name,
                'concept_description': prompt_data.get('description', ''),
                'prompt': prompt_data.get('prompt', ''),
                'models': models_to_use
            })

            # Generate with all models for this concept
            concept_results = {}

            def generate_for_model(model_name):
                result = generator.generate_with_model(
                    model_name, prompt_data, f"{batch_id}/concept_{concept_idx}/{model_name}"
                )
                return model_name, result

            # Run all models in parallel for this concept
            with ThreadPoolExecutor(max_workers=len(models_to_use)) as executor:
                futures = [executor.submit(generate_for_model, m) for m in models_to_use]

                for future in as_completed(futures):
                    try:
                        model_name, result = future.result()
                    except Exception as e:
                        print(f"[PARALLEL-GEN] Future failed: {e}")
                        continue

                    if result.get('success'):
                        file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')

                        # Auto-composite logos
                        _apply_logos_to_image(file_path, titles_raw, creative_direction, concept_name)

                        concept_results[model_name] = file_path

                        # Save to history
                        job_manager.add_result(job_id, {
                            'file_path': file_path,
                            'model': model_name,
                            'concept_name': concept_name,
                            'prompt': prompt_data.get('prompt', ''),
                            'description': prompt_data.get('description', ''),
                            'category': prompt_data.get('category', ''),
                            'title_ref': prompt_data.get('title_ref', ''),
                            'batch_id': batch_id,
                            'video_name': video_name,
                        })

                        yield sse_message({
                            'type': 'model_result',
                            'concept_index': concept_idx,
                            'concept_name': concept_name,
                            'model': model_name,
                            'file_path': file_path,
                            'prompt': prompt_data.get('prompt', ''),
                            'description': prompt_data.get('description', ''),
                            'category': prompt_data.get('category', ''),
                            'title_ref': prompt_data.get('title_ref', '')
                        })
                    else:
                        yield sse_message({
                            'type': 'model_error',
                            'concept_index': concept_idx,
                            'model': model_name,
                            'error': result.get('error', 'Unknown')[:100]
                        })

            yield sse_message({
                'type': 'concept_complete',
                'concept_index': concept_idx,
                'concept_name': concept_name,
                'results': concept_results
            })

        # Complete the job
        job_manager.complete_job(job_id, success=True)

        yield sse_message({
            'type': 'shootout_complete',
            'total_concepts': len(prompts_with_concepts),
            'models': models_to_use,
            'message': f'Shootout complete! Compare {len(prompts_with_concepts)} concepts across {len(models_to_use)} models'
        })

    return sse_response(generate_stream())


# ============================================================
# MULTI-MODEL COMPARISON (Feature #3)
# ============================================================

@app.route('/compare-models')
def compare_models():
    """
    Generate the same prompt with multiple models for comparison.

    Query params:
    - prompt: The image generation prompt
    - concept_name: Name for the concept
    """
    prompt = request.args.get('prompt', '')
    concept_name = request.args.get('concept_name', 'comparison')

    if not prompt:
        return Response(
            sse_message({'type': 'error', 'message': 'No prompt provided'}),
            mimetype='text/event-stream'
        )

    def compare_stream():
        generator = _make_generator()
        available = generator.get_available_models()

        yield sse_message({
            'type': 'progress',
            'message': f'Comparing {len(available)} models: {", ".join(available)}'
        })

        prompt_data = {
            'prompt': prompt,
            'concept_name': concept_name,
        }

        results = generator.generate_with_all(prompt_data, "comparison")

        for model_name, result in results.items():
            if result.get('success'):
                file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                yield sse_message({
                    'type': 'thumbnail',
                    'file_path': file_path,
                    'model': model_name,
                    'concept_name': concept_name,
                })
            else:
                yield sse_message({
                    'type': 'error',
                    'model': model_name,
                    'message': result.get('error', 'Unknown error')
                })

        yield sse_message({
            'type': 'complete',
            'message': 'Model comparison complete'
        })

    return Response(compare_stream(), mimetype='text/event-stream')


# ============================================================
# EDIT MODE - Quick Iteration & Text Overlays (NEW)
# ============================================================

# Store active iteration sessions
_iteration_sessions = {}


@app.route('/edit/<path:image_path>')
def edit_page(image_path):
    """Serve the edit page for a specific thumbnail."""
    return render_template('edit.html', image_path=image_path)


@app.route('/api/refine', methods=['POST'])
def refine_prompt():
    """
    Refine a prompt based on natural language feedback.

    POST body:
    - original_prompt: The current prompt
    - feedback: What to change (e.g., "make it more dramatic")
    - session_id: Optional session ID for history
    """
    data = request.json
    original_prompt = data.get('original_prompt', '')
    feedback = data.get('feedback', '')
    session_id = data.get('session_id')

    if not original_prompt or not feedback:
        return jsonify({'success': False, 'error': 'Missing prompt or feedback'})

    refiner = ThumbnailRefiner(settings)

    # Get conversation history if session exists
    history = []
    if session_id and session_id in _iteration_sessions:
        history = _iteration_sessions[session_id].get_conversation_history()

    result = refiner.refine_prompt(original_prompt, feedback, history)

    return jsonify(result)


@app.route('/api/refine-and-generate', methods=['POST'])
def refine_and_generate():
    """
    Refine a prompt AND generate a new image in one step.

    POST body:
    - original_prompt: The current prompt
    - feedback: What to change
    - model: Which image model to use
    - session_id: Optional session ID
    """
    data = request.json
    original_prompt = data.get('original_prompt', '')
    feedback = data.get('feedback', '')
    model_key = data.get('model', 'gemini')
    session_id = data.get('session_id')

    if not original_prompt or not feedback:
        return jsonify({'success': False, 'error': 'Missing prompt or feedback'})

    def generate_stream():
        # Step 1: Refine the prompt
        yield sse_message({'type': 'progress', 'message': 'Refining prompt...'})

        refiner = ThumbnailRefiner(settings)
        history = []
        if session_id and session_id in _iteration_sessions:
            history = _iteration_sessions[session_id].get_conversation_history()

        refine_result = refiner.refine_prompt(original_prompt, feedback, history)

        if not refine_result.get('success'):
            yield sse_message({'type': 'error', 'message': 'Failed to refine prompt'})
            return

        new_prompt = refine_result['new_prompt']
        changes = refine_result.get('changes', '')

        yield sse_message({
            'type': 'refined',
            'new_prompt': new_prompt,
            'changes': changes
        })

        # Step 2: Generate new image
        yield sse_message({'type': 'progress', 'message': 'Generating new image...'})

        generator = _make_generator()
        prompt_data = {
            'prompt': new_prompt,
            'concept_name': f'refined_{datetime.now().strftime("%H%M%S")}',
        }

        result = generator.generate_with_model(model_key, prompt_data, "refined")

        if result.get('success'):
            file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
            yield sse_message({
                'type': 'complete',
                'file_path': file_path,
                'prompt': new_prompt,
                'changes': changes,
                'model': model_key
            })
        else:
            yield sse_message({
                'type': 'error',
                'message': f'Generation failed: {result.get("error", "Unknown")}'
            })

    return sse_response(generate_stream())


@app.route('/api/quick-generate', methods=['POST'])
def quick_generate():
    """
    Generate an image directly from a prompt (no refinement).
    For quick iteration when you've manually edited the prompt.
    """
    data = request.json
    prompt = data.get('prompt', '')
    model_key = data.get('model', 'gemini')

    if not prompt:
        return jsonify({'success': False, 'error': 'No prompt provided'})

    generator = _make_generator()
    prompt_data = {
        'prompt': prompt,
        'concept_name': f'quick_{datetime.now().strftime("%H%M%S")}',
    }

    result = generator.generate_with_model(model_key, prompt_data, "quick")

    if result.get('success'):
        file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
        return jsonify({
            'success': True,
            'file_path': file_path,
            'prompt': prompt
        })
    else:
        return jsonify({
            'success': False,
            'error': result.get('error', 'Unknown error')
        })


@app.route('/api/suggestions', methods=['POST'])
def get_suggestions():
    """Get refinement suggestions for a prompt."""
    data = request.json
    prompt = data.get('prompt', '')

    refiner = ThumbnailRefiner(settings)
    suggestions = refiner.suggest_refinements(prompt)

    return jsonify({'suggestions': suggestions})


def _find_original_image(image_path):
    """Find the _original (no-text) version of an image if it exists, otherwise return the image itself."""
    p = Path(image_path)
    # Check for _original sibling (saved before text was applied)
    for ext in [p.suffix, '.png', '.jpg', '.jpeg']:
        original = p.parent / f"{p.stem}_original{ext}"
        if original.exists():
            return original
    # Also check if this IS the _original already
    return p


@app.route('/api/add-text', methods=['POST'])
def add_text_to_image():
    """
    Add text overlay to a thumbnail.

    POST body:
    - image_path: Path to the image (relative to output dir)
    - text: The text to add
    - position: Where to put it (top-left, center, bottom-right, etc.)
    - style: Text style (impact, subtitle, number, label)
    - color: Optional custom color
    """
    data = request.json
    image_path = data.get('image_path', '')
    text = data.get('text', '')
    position = data.get('position', 'bottom-center')
    style = data.get('style', 'impact')
    color = data.get('color')
    y_ratio = data.get('y_ratio')
    font_size_ratio = data.get('font_size_ratio')

    if not image_path or not text:
        return jsonify({'success': False, 'error': 'Missing image_path or text'})

    # Build full path - prefer _original (no-text) version for clean overlays
    full_path = _find_original_image(settings.output_dir / image_path)

    if not full_path.exists():
        return jsonify({'success': False, 'error': 'Image not found'})

    try:
        overlay = TextOverlay()
        output_path = overlay.add_text(
            image_path=str(full_path),
            text=text,
            position=position,
            style=style,
            custom_color=color,
            y_ratio=float(y_ratio) if y_ratio is not None else None,
            font_size_ratio=float(font_size_ratio) if font_size_ratio is not None else None,
        )

        # Return relative path
        rel_path = str(Path(output_path).relative_to(settings.output_dir))

        return jsonify({
            'success': True,
            'file_path': rel_path,
            'original_path': image_path
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/text-styles')
def get_text_styles():
    """Get available text styles for the UI."""
    overlay = TextOverlay()
    return jsonify({
        'styles': overlay.get_available_styles(),
        'positions': list(overlay.POSITIONS.keys())
    })


@app.route('/api/analyze-text-zones', methods=['POST'])
def analyze_text_zones():
    """
    Use Claude Vision to analyze an image and find safe zones for text placement.

    POST body:
    - image_path: Path to the image (relative to output dir)
    """
    data = request.json
    image_path = data.get('image_path', '')

    if not image_path:
        return jsonify({'success': False, 'error': 'No image_path provided'})

    # Build full path
    full_path = settings.output_dir / image_path

    if not full_path.exists():
        return jsonify({'success': False, 'error': 'Image not found'})

    try:
        overlay = TextOverlay()
        analysis = overlay.analyze_safe_zones(str(full_path))
        return jsonify({
            'success': True,
            'analysis': analysis
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/generate-text-variations', methods=['POST'])
def generate_text_variations():
    """
    Generate multiple versions of a thumbnail with different text overlays.

    POST body:
    - image_path: Path to the source image (relative to output dir)
    - text_copies: List of text strings to overlay
    - position: Where to place text (optional - will auto-detect if not provided)
    - style: Text style (impact, subtitle, number, label)
    """
    data = request.json
    image_path = data.get('image_path', '')
    text_copies = data.get('text_copies', [])
    position = data.get('position')  # None = auto-detect
    style = data.get('style', 'impact')

    if not image_path:
        return jsonify({'success': False, 'error': 'No image_path provided'})

    if not text_copies:
        return jsonify({'success': False, 'error': 'No text_copies provided'})

    # Build full path - prefer _original (no-text) version for clean overlays
    full_path = _find_original_image(settings.output_dir / image_path)

    if not full_path.exists():
        return jsonify({'success': False, 'error': 'Image not found'})

    try:
        overlay = TextOverlay()

        # Create output directory for text variations
        text_output_dir = settings.output_dir / "text_variations"
        text_output_dir.mkdir(parents=True, exist_ok=True)

        # First analyze for best position if not specified
        analysis = None
        if position is None:
            analysis = overlay.analyze_safe_zones(str(full_path))
            recommended = analysis.get("recommended_positions", ["top-left"])
            position = recommended[0] if recommended else "top-left"

        # Generate all variations
        results = overlay.generate_text_variations(
            image_path=str(full_path),
            text_copies=text_copies,
            position=position,
            style=style,
            output_dir=str(text_output_dir)
        )

        # Convert file paths to relative paths for the frontend
        for result in results:
            if result.get('file_path'):
                result['file_path'] = str(Path(result['file_path']).relative_to(settings.output_dir))

        return jsonify({
            'success': True,
            'position_used': position,
            'analysis': analysis,
            'variations': results
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# PARALLEL GENERATION - Generate with ALL models at once
# ============================================================

@app.route('/api/parallel-generate')
def parallel_generate():
    """
    Generate concepts with Claude, then render with multiple models IN PARALLEL.
    Returns a stream of results as each model completes.

    Query params:
    - titles: Newline-separated video titles
    - script: Optional video script for context
    - count: Number of concepts to generate
    - models: Comma-separated list of models to use
    - use_favorites: Whether to learn from favorites
    """
    err = _require_video_name()
    if err: return err
    titles_raw = request.args.get('titles', '')
    script = request.args.get('script', '')
    creative_direction = request.args.get('creative_direction', '')
    video_name = request.args.get('video_name', '')
    count = int(request.args.get('count', 10))
    models_str = request.args.get('models', 'nanobanana2')
    use_favorites = request.args.get('use_favorites', 'true').lower() == 'true'

    selected_models = [m.strip() for m in models_str.split(',') if m.strip()]
    titles = [t.strip() for t in titles_raw.split('\n') if t.strip()]

    if not titles:
        return Response(
            sse_message({'type': 'error', 'message': 'No titles provided'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        # Initialize components (pass prompt_manager so edits take effect)
        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()
        favorites_mgr = FavoritesManager(settings)
        freshness = FreshnessTracker(settings)

        available_models = generator.get_available_models()
        models_to_use = [m for m in selected_models if m in available_models]

        if not models_to_use:
            yield sse_message({'type': 'error', 'message': 'No valid models selected'})
            return

        # Get favorites context
        favorites_context = ""
        if use_favorites:
            favorites_context = favorites_mgr.get_favorites_summary_for_prompt(limit=5)

        # PHASE 1+2 COMBINED: Generate concepts AND prompts in one Claude call
        yield sse_message({
            'type': 'progress',
            'message': 'Claude is generating concepts + prompts (single call)...'
        })

        try:
            prompts_with_concepts = ideator.generate_concepts_and_prompts(
                titles=titles,
                used_ideas=freshness.get_summary_list(),
                batch_number=1,
                script=script,
                favorites_context=favorites_context,
                count=count
            )
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
            return

        if not prompts_with_concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated'})
            return

        # Limit to requested count
        prompts_with_concepts = prompts_with_concepts[:count]

        yield sse_message({
            'type': 'progress',
            'message': f'Got {len(prompts_with_concepts)} concepts with prompts, generating images...'
        })

        # PHASE 3: Parallel generation with all models
        total_images = len(prompts_with_concepts) * len(models_to_use)

        yield sse_message({
            'type': 'parallel_start',
            'models': models_to_use,
            'total_models': len(models_to_use),
            'concepts_per_model': len(prompts_with_concepts),
            'total': total_images,
            'message': f'Generating {total_images} images ({len(prompts_with_concepts)} concepts × {len(models_to_use)} models)...'
        })

        # Initialize model status
        for model in models_to_use:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'Starting...',
                'progress': 0,
                'total': len(prompts_with_concepts)
            })

        completed_per_model = {m: 0 for m in models_to_use}
        total_completed = 0
        batch_id = f"parallel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def generate_one(model_name, prompt_data, index):
            """Generate a single image with a specific model."""
            result = generator.generate_with_model(model_name, prompt_data, f"{batch_id}/{model_name}")
            return model_name, prompt_data, result, index

        # Create all tasks
        tasks = []
        for idx, prompt_data in enumerate(prompts_with_concepts):
            for model in models_to_use:
                tasks.append((model, prompt_data, idx))

        # Execute in parallel (limit workers to prevent API overload)
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            futures = [executor.submit(generate_one, m, p, i) for m, p, i in tasks]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Generation stopped'})
                    return

                try:
                    model_name, prompt_data, result, idx = future.result()
                except Exception as e:
                    print(f"[PARALLEL-VAR] Future failed: {e}")
                    continue
                completed_per_model[model_name] += 1
                total_completed += 1

                if result.get('success'):
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                    freshness.add_used_idea(prompt_data)

                    # Auto-composite logos
                    _apply_logos_to_image(file_path, titles_raw, creative_direction, prompt_data.get('concept_name', ''))

                    template_label = creative_direction.split(' — ')[0].strip() if creative_direction else ''
                    thumbnail_data = {
                        'type': 'model_thumbnail',
                        'model': model_name,
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': prompt_data.get('description', ''),
                        'category': prompt_data.get('category', ''),
                        'prompt': prompt_data.get('prompt', ''),
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts),
                        'video_name': video_name,
                        'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                        'template': template_label,
                    }

                    # Save to history
                    job_manager.add_result(batch_id, thumbnail_data)

                    yield sse_message(thumbnail_data)

                    # Update model progress
                    yield sse_message({
                        'type': 'model_progress',
                        'model': model_name,
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts)
                    })
                else:
                    yield sse_message({
                        'type': 'model_error',
                        'model': model_name,
                        'error': result.get('error', 'Unknown error')[:100]
                    })

        # Mark models complete
        for model in models_to_use:
            yield sse_message({
                'type': 'model_complete',
                'model': model,
                'count': completed_per_model[model]
            })

        yield sse_message({
            'type': 'parallel_complete',
            'total_generated': total_completed,
            'models': models_to_use,
            'message': f'Generated {total_completed} images across {len(models_to_use)} models'
        })

    return sse_response(generate_stream())


@app.route('/api/template-generate')
def template_generate():
    """
    Generate a composite template thumbnail.

    Query params:
    - template: Template type (levels, pyramid, grid, vs_split)
    - topic: The topic/theme
    - slots: Number of slots
    - model: Image model to use
    """
    from lib.template_engine import TEMPLATES, get_claude_instruction, TemplateCompositor

    template_key = request.args.get('template', 'levels')
    topic = request.args.get('topic', '')
    slots = int(request.args.get('slots', TEMPLATES.get(template_key, {}).get('default_slots', 7)))
    model_name = request.args.get('model', 'nanobanana2')

    if not topic:
        return Response(
            sse_message({'type': 'error', 'message': 'No topic provided'}),
            mimetype='text/event-stream'
        )

    if template_key not in TEMPLATES:
        return Response(
            sse_message({'type': 'error', 'message': f'Unknown template: {template_key}'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()

        available_models = generator.get_available_models()
        if model_name not in available_models:
            yield sse_message({'type': 'error', 'message': f'Model {model_name} not available'})
            return

        # PHASE 1: Generate slot concepts with Claude
        yield sse_message({
            'type': 'progress',
            'message': f'Claude is planning {slots} slots for "{topic}"...',
            'phase': 'concepts'
        })

        template_instruction = get_claude_instruction(template_key, topic, slots)
        prompt = f"""{template_instruction}

Return as JSON:
```json
{{
  "slots": [
    {{
      "slot_number": 1,
      "label": "Short label (2-4 words)",
      "description": "Vivid 1-2 sentence visual description for image generation"
    }}
  ]
}}
```

Generate exactly {slots} slots. Each description should be a SINGLE clear visual scene."""

        try:
            response = ideator._stream_with_retry(
                model=ideator.model,
                max_tokens=16000,
                thinking={"type": "enabled", "budget_tokens": ideator.budget_tokens},
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    response_text = block.text

            # Parse slots from response
            import re
            json_match = re.search(r'\{[\s\S]*"slots"[\s\S]*\}', response_text)
            if not json_match:
                yield sse_message({'type': 'error', 'message': 'Failed to parse slot concepts'})
                return

            slot_data = json.loads(json_match.group())
            slot_concepts = slot_data.get('slots', [])[:slots]

        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
            return

        if not slot_concepts:
            yield sse_message({'type': 'error', 'message': 'No slot concepts generated'})
            return

        yield sse_message({
            'type': 'progress',
            'message': f'Got {len(slot_concepts)} slot concepts, generating image prompts...',
            'phase': 'prompts',
            'slots': [s.get('label', f'Slot {s.get("slot_number", i+1)}') for i, s in enumerate(slot_concepts)]
        })

        # PHASE 2: Generate image prompts for each slot
        concepts_for_prompts = [
            {
                'concept_name': s.get('label', f'Slot {i+1}'),
                'description': s.get('description', ''),
                'category': template_key,
            }
            for i, s in enumerate(slot_concepts)
        ]

        try:
            prompts_with_concepts = ideator.generate_prompts_for_concepts(concepts_for_prompts)
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Prompt generation error: {str(e)}'})
            return

        # PHASE 3: Generate images in parallel
        yield sse_message({
            'type': 'progress',
            'message': f'Generating {len(prompts_with_concepts)} images with {model_name}...',
            'phase': 'images',
            'total': len(prompts_with_concepts)
        })

        batch_id = f"template_{template_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        image_paths = [None] * len(prompts_with_concepts)
        completed = 0

        def generate_one(idx, prompt_data):
            result = generator.generate_with_model(model_name, prompt_data, f"{batch_id}/{model_name}")
            return idx, result

        with ThreadPoolExecutor(max_workers=min(4, len(prompts_with_concepts))) as executor:
            futures = [executor.submit(generate_one, i, p) for i, p in enumerate(prompts_with_concepts)]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Stopped'})
                    return

                try:
                    idx, result = future.result()
                except Exception as e:
                    print(f"[TEMPLATE] Image generation failed: {e}")
                    continue

                completed += 1

                if result.get('success'):
                    image_paths[idx] = result['file_path']
                    yield sse_message({
                        'type': 'slot_complete',
                        'slot': idx,
                        'label': slot_concepts[idx].get('label', f'Slot {idx+1}') if idx < len(slot_concepts) else f'Slot {idx+1}',
                        'file_path': result['file_path'].replace(str(settings.output_dir) + '/', ''),
                        'current': completed,
                        'total': len(prompts_with_concepts)
                    })
                else:
                    yield sse_message({
                        'type': 'slot_error',
                        'slot': idx,
                        'error': result.get('error', 'Unknown')[:100],
                        'current': completed,
                        'total': len(prompts_with_concepts)
                    })

        # PHASE 4: Composite into template
        valid_paths = [p for p in image_paths if p is not None]
        if len(valid_paths) < 2:
            yield sse_message({'type': 'error', 'message': f'Only {len(valid_paths)} images succeeded, need at least 2'})
            return

        yield sse_message({
            'type': 'progress',
            'message': 'Compositing into template layout...',
            'phase': 'composite'
        })

        try:
            compositor = TemplateCompositor()
            labels = [s.get('label', f'Slot {i+1}') for i, s in enumerate(slot_concepts)]

            # Use valid paths only, fill gaps with first valid image
            final_paths = []
            for p in image_paths:
                if p is not None:
                    final_paths.append(p)
                else:
                    final_paths.append(valid_paths[0])

            output_dir = settings.output_dir / batch_id
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"template_{template_key}.png")

            result_path = compositor.composite(
                template_key=template_key,
                images=final_paths,
                labels=labels,
                output_path=output_path,
            )

            rel_path = str(Path(result_path).relative_to(settings.output_dir))

            yield sse_message({
                'type': 'template_complete',
                'file_path': rel_path,
                'template': template_key,
                'topic': topic,
                'slots': len(final_paths),
                'message': f'Template thumbnail generated!'
            })

        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Compositing error: {str(e)}'})

    return sse_response(generate_stream())


@app.route('/api/templates')
def get_templates():
    """Return available template definitions."""
    from lib.template_engine import get_template_info
    return jsonify({'success': True, 'templates': get_template_info()})


def _run_agentic_generation(store_job_id, titles, titles_raw, script, creative_direction,
                              video_name, count, selected_models, use_favorites,
                              max_iterations, quality_threshold, thumbnail_text):
    """
    Background generation function — runs in a thread, pushes events to job_event_store.
    Completely decoupled from SSE/browser connection. Survives page refresh.
    """
    global _stop_generation
    _stop_generation = False

    def emit(event_dict):
        """Push an event to the store (replaces yield sse_message)."""
        job_event_store.push_event(store_job_id, event_dict)

    # Initialize components
    ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
    generator = _make_generator()
    refiner = AgenticImageRefiner(settings, max_iterations=max_iterations, quality_threshold=quality_threshold)
    favorites_mgr = FavoritesManager(settings)
    freshness = FreshnessTracker(settings)

    available_models = generator.get_available_models()
    models_to_use = [m for m in selected_models if m in available_models]

    if not models_to_use:
        emit({'type': 'error', 'message': 'No valid models selected'})
        job_event_store.complete_job(store_job_id, 'error')
        return

    # Get favorites context
    favorites_context = ""
    if use_favorites:
        favorites_context = favorites_mgr.get_favorites_summary_for_prompt(limit=5)

    emit({
        'type': 'agentic_start',
        'models': models_to_use,
        'max_iterations': max_iterations,
        'quality_threshold': quality_threshold,
        'message': f'Starting agentic generation with {len(models_to_use)} models (up to {max_iterations} refinement iterations)'
    })

    # PHASE 1+2 COMBINED: Generate concepts AND prompts in one Claude call
    emit({
        'type': 'progress',
        'phase': 'ideation',
        'message': 'Claude is generating concepts + prompts (single fast call)...'
    })
    emit({'type': 'claude_prompt', 'content': 'Generating concepts and prompts in one call...'})
    emit({'type': 'claude_thinking_start'})

    combined_queue = queue.Queue()
    def _stream_combined():
        try:
            for event in ideator.generate_concepts_and_prompts_streaming(
                titles=titles,
                used_ideas=freshness.get_summary_list(),
                batch_number=1,
                script=script,
                favorites_context=favorites_context,
                creative_direction=creative_direction,
                count=count
            ):
                combined_queue.put(event)
        except Exception as e:
            combined_queue.put({'type': 'error', 'error': str(e)})
        finally:
            combined_queue.put(None)  # sentinel

    threading.Thread(target=_stream_combined, daemon=True).start()

    prompts_with_concepts = None
    while True:
        try:
            event = combined_queue.get(timeout=5)
        except queue.Empty:
            continue  # No keepalive needed — not tied to SSE
        if event is None:
            break
        etype = event.get('type')
        if etype == 'error':
            emit({'type': 'error', 'message': f'Claude error: {event["error"]}'})
            job_event_store.complete_job(store_job_id, 'error')
            return
        elif etype == 'prompt':
            emit({'type': 'claude_prompt', 'content': event['content']})
        elif etype == 'thinking_start':
            emit({'type': 'claude_thinking_start'})
        elif etype == 'thinking_delta':
            emit({'type': 'claude_thinking', 'content': event['content']})
        elif etype == 'response_start':
            emit({'type': 'claude_response_start'})
        elif etype == 'response_delta':
            emit({'type': 'claude_response', 'content': event['content']})
        elif etype == 'complete':
            emit({'type': 'claude_complete'})
        elif etype == 'prompts_ready':
            prompts_with_concepts = event['prompts']

    if not prompts_with_concepts:
        emit({'type': 'error', 'message': 'No concepts generated'})
        job_event_store.complete_job(store_job_id, 'error')
        return

    prompts_with_concepts = prompts_with_concepts[:count]

    # PHASE 3: Agentic refinement loop
    batch_id = f"agentic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Create a job for history tracking
    job_id = None
    try:
        job_id = job_manager.create_job('agentic', {
            'titles': titles,
            'creative_direction': creative_direction,
            'video_name': video_name,
            'models': models_to_use,
            'count': count,
            'max_iterations': max_iterations,
            'quality_threshold': quality_threshold
        })

        all_iterations = []

        for concept_idx, prompt_data in enumerate(prompts_with_concepts):
            if _stop_generation:
                job_manager.complete_job(job_id, success=False)
                emit({'type': 'stopped', 'message': 'Generation stopped'})
                job_event_store.complete_job(store_job_id)
                return

            concept_name = prompt_data.get('concept_name', f'concept_{concept_idx+1}')

            emit({
                'type': 'concept_start',
                'concept_name': concept_name,
                'concept_num': concept_idx + 1,
                'total_concepts': len(prompts_with_concepts),
                'message': f'Processing concept {concept_idx+1}/{len(prompts_with_concepts)}: {concept_name}'
            })

            current_prompt_data = prompt_data.copy()
            iteration_history = []

            # Refinement loop for this concept
            for iteration in range(max_iterations):
                if _stop_generation:
                    break

                emit({
                    'type': 'iteration_start',
                    'concept_name': concept_name,
                    'iteration': iteration + 1,
                    'message': f'Iteration {iteration+1}/{max_iterations}: Generating with {len(models_to_use)} models...'
                })

                # Generate with all models IN PARALLEL
                results = {}
                failed_models = []
                img_results_queue = queue.Queue()

                def generate_for_model(model_name):
                    try:
                        prompt_data_for_gen = current_prompt_data
                        if thumbnail_text:
                            prompt_data_for_gen = dict(current_prompt_data)
                            prompt_data_for_gen['prompt'] = (
                                current_prompt_data.get('prompt', '') +
                                f'\n\nIMPORTANT: Leave the bottom 20% of the image as a clean, uncluttered area for text overlay. Do NOT include any text, words, or letters anywhere in the image.'
                            )
                        result = generator.generate_with_model(
                            model_name,
                            prompt_data_for_gen,
                            f"{batch_id}/iter{iteration+1}/{model_name}"
                        )
                        img_results_queue.put((model_name, result))
                    except Exception as e:
                        img_results_queue.put((model_name, {'success': False, 'error': str(e)}))

                executor = ThreadPoolExecutor(max_workers=len(models_to_use))
                for m in models_to_use:
                    executor.submit(generate_for_model, m)

                received = 0
                while received < len(models_to_use):
                    if _stop_generation:
                        break
                    try:
                        model_name, result = img_results_queue.get(timeout=3)
                        received += 1
                    except queue.Empty:
                        continue  # No keepalive needed

                    if result.get('success'):
                        results[model_name] = result

                        # Show the generated image
                        file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')

                        # Apply text overlay if thumbnail_text provided
                        original_file_path = None
                        if thumbnail_text:
                            try:
                                abs_path = str(settings.output_dir / file_path)
                                # Save original (no-text) copy
                                orig_path = Path(abs_path)
                                original_abs = str(orig_path.parent / f"{orig_path.stem}_original{orig_path.suffix}")
                                import shutil
                                shutil.copy2(abs_path, original_abs)
                                original_file_path = str(Path(original_abs).relative_to(settings.output_dir))

                                text_overlay_obj = TextOverlay()
                                text_overlay_obj.add_text(
                                    abs_path,
                                    thumbnail_text,
                                    position='top-center',
                                    style='impact',
                                    output_path=abs_path
                                )
                            except Exception as te:
                                print(f"[TEXT OVERLAY] Failed for {file_path}: {te}")

                        # Auto-composite logos if detected in title/creative direction
                        _apply_logos_to_image(file_path, titles_raw, creative_direction, concept_name)

                        # Save to history
                        # Extract short layout label from creative direction (before the " — ")
                        template_label = creative_direction.split(' — ')[0].strip() if creative_direction else ''
                        result_record = {
                            'file_path': file_path,
                            'model': model_name,
                            'concept_name': concept_name,
                            'prompt': current_prompt_data.get('prompt', ''),
                            'description': current_prompt_data.get('description', ''),
                            'category': current_prompt_data.get('category', ''),
                            'title_ref': current_prompt_data.get('title_ref', ''),
                            'batch_id': batch_id,
                            'iteration': iteration + 1,
                            'agentic_score': None,
                            'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                            'template': template_label,
                            'video_name': video_name,
                        }
                        if thumbnail_text:
                            result_record['thumbnail_text'] = thumbnail_text
                            if original_file_path:
                                result_record['original_file_path'] = original_file_path
                        job_manager.add_result(job_id, result_record)

                        sse_data = {
                            'type': 'image_generated',
                            'model': model_name,
                            'file_path': file_path,
                            'concept_name': concept_name,
                            'concept_summary': current_prompt_data.get('description', ''),
                            'prompt': current_prompt_data.get('prompt', ''),
                            'title_ref': current_prompt_data.get('title_ref', ''),
                            'category': current_prompt_data.get('category', ''),
                            'iteration': iteration + 1,
                            'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                            'template': template_label,
                        }
                        if thumbnail_text:
                            sse_data['thumbnail_text'] = thumbnail_text
                            if original_file_path:
                                sse_data['original_file_path'] = original_file_path
                        emit(sse_data)
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        failed_models.append(f"{model_name}: {error_msg}")
                        print(f"[AGENTIC ERROR] {model_name} failed for '{concept_name}': {error_msg}")
                        emit({
                            'type': 'phase',
                            'message': f'⚠️ {model_name} failed: {error_msg[:80]}'
                        })

                executor.shutdown(wait=True)

                if not results:
                    error_details = '; '.join(failed_models) if failed_models else 'No error details'
                    emit({
                        'type': 'error',
                        'message': f'All models failed for concept: {concept_name}. Errors: {error_details}'
                    })
                    print(f"[AGENTIC ERROR] All models failed for '{concept_name}'. Skipping.")
                    break

                # Skip evaluation on the last iteration (nothing to refine)
                is_last_iteration = (iteration >= max_iterations - 1)

                if is_last_iteration:
                    evaluations = []
                else:
                    # Evaluate quality with Claude (only when refinement will follow)
                    emit({
                        'type': 'evaluating',
                        'concept_name': concept_name,
                        'iteration': iteration + 1,
                        'message': 'Claude evaluating all thumbnails (batch)...'
                    })

                    images_data = []
                    for model_name, result in results.items():
                        images_data.append({
                            'image_path': Path(result['file_path']),
                            'prompt_used': current_prompt_data.get('prompt', ''),
                            'concept_name': concept_name,
                            'model': model_name
                        })

                    try:
                        evaluations = refiner.evaluate_thumbnails_batch(images_data) or []
                    except Exception as eval_err:
                        print(f"[AGENTIC] Evaluation error: {eval_err}")
                        emit({'type': 'warning', 'message': f'Evaluation failed: {str(eval_err)[:100]}'})
                        evaluations = []

                # Send results to frontend AND update history
                for idx, (model_name, result) in enumerate(results.items()):
                    if idx < len(evaluations):
                        eval_result = evaluations[idx]
                        eval_result['file_path'] = result['file_path'].replace(str(settings.output_dir) + '/', '')

                        job_manager.update_result(job_id, eval_result['file_path'], {
                            'agentic_score': eval_result.get('score', 0),
                            'description': eval_result.get('analysis', '')
                        })

                        emit({
                            'type': 'evaluation_result',
                            'model': model_name,
                            'score': eval_result.get('score', 0),
                            'analysis': eval_result.get('analysis', ''),
                            'file_path': eval_result['file_path'],
                            'concept_name': concept_name,
                            'prompt_used': current_prompt_data.get('prompt', ''),
                            'iteration': iteration + 1
                        })

                scores = [e.get('score', 0) for e in evaluations]
                avg_score = sum(scores) / len(scores) if scores else 0

                iteration_history.append({
                    'iteration': iteration + 1,
                    'evaluations': evaluations,
                    'avg_score': avg_score,
                    'prompt': current_prompt_data.get('prompt', '')
                })

                emit({
                    'type': 'iteration_complete',
                    'concept_name': concept_name,
                    'iteration': iteration + 1,
                    'avg_score': avg_score,
                    'message': f'Iteration {iteration+1} complete: Average quality score {avg_score:.1f}/10'
                })

                # Last iteration? Don't refine
                if iteration >= max_iterations - 1:
                    emit({
                        'type': 'max_iterations_reached',
                        'concept_name': concept_name,
                        'final_score': avg_score,
                        'message': f'Max iterations reached. Final score: {avg_score:.1f}/10'
                    })
                    break

                # Refine the prompt for next iteration
                emit({
                    'type': 'refining',
                    'concept_name': concept_name,
                    'iteration': iteration + 1,
                    'message': 'Claude is refining the prompt...'
                })

                try:
                    current_prompt_data = refiner.refine_prompt_batch(evaluations, current_prompt_data)
                except Exception as e:
                    print(f"[AGENTIC] Prompt refinement failed: {e}")

                emit({
                    'type': 'prompt_refined',
                    'concept_name': concept_name,
                    'new_prompt': current_prompt_data.get('prompt', ''),
                    'iteration': iteration + 2,
                    'message': f'Prompt refined. Starting iteration {iteration+2}...'
                })

            # Concept complete
            final_avg = iteration_history[-1]['avg_score'] if iteration_history else 0
            all_iterations.append({
                'concept_name': concept_name,
                'iterations': iteration_history,
                'final_score': final_avg
            })

            emit({
                'type': 'concept_complete',
                'concept_name': concept_name,
                'final_score': final_avg,
                'total_iterations': len(iteration_history),
                'message': f'Concept complete: {concept_name} (final score: {final_avg:.1f}/10)'
            })

        # All done!
        overall_avg = sum(c['final_score'] for c in all_iterations) / len(all_iterations) if all_iterations else 0
        job_manager.complete_job(job_id, success=True)

        emit({
            'type': 'agentic_complete',
            'total_concepts': len(all_iterations),
            'overall_avg_score': overall_avg,
            'message': f'Agentic generation complete! Overall average quality: {overall_avg:.1f}/10'
        })

    except Exception as e:
        print(f"[AGENTIC ERROR] Unhandled exception: {e}")
        import traceback
        traceback.print_exc()
        if job_id:
            job_manager.complete_job(job_id, success=False)
        emit({'type': 'error', 'message': f'Generation error: {str(e)}'})

    job_event_store.complete_job(store_job_id)


@app.route('/api/agentic-generate')
def agentic_generate():
    """
    Start agentic image generation in background.
    Returns job_id immediately. Use /api/jobs/<job_id>/stream to watch progress.
    Also supports legacy SSE mode (auto-streams for backward compatibility).
    """
    err = _require_video_name()
    if err: return err
    titles_raw = request.args.get('titles', '')
    script = request.args.get('script', '')
    creative_direction = request.args.get('creative_direction', '').strip()
    video_name = request.args.get('video_name', '')
    _auto_cleanup_if_needed()  # Prevent disk-full crashes
    count = min(int(request.args.get('count', 10)), 100)
    models_str = request.args.get('models', 'nanobanana2')
    use_favorites = request.args.get('use_favorites', 'true').lower() == 'true'
    max_iterations = int(request.args.get('max_iterations', 2))
    quality_threshold = float(request.args.get('quality_threshold', 9.0))
    thumbnail_text = request.args.get('thumbnail_text', '').strip()

    selected_models = [m.strip() for m in models_str.split(',') if m.strip()]
    titles = [t.strip() for t in titles_raw.split('\n') if t.strip()]

    if not titles:
        return jsonify({'error': 'No titles provided'}), 400

    # Create store job and start background generation
    store_job_id = f"sj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(threading.current_thread()) % 10000}"
    job_event_store.create_job(store_job_id, {
        'titles': titles,
        'creative_direction': creative_direction,
        'video_name': video_name,
        'models': selected_models,
        'count': count,
        'thumbnail_text': thumbnail_text,
    })

    thread = threading.Thread(
        target=_run_agentic_generation,
        args=(store_job_id, titles, titles_raw, script, creative_direction,
              video_name, count, selected_models, use_favorites,
              max_iterations, quality_threshold, thumbnail_text),
        daemon=True
    )
    thread.start()

    # If mode=start, return job_id as JSON (for frontend to connect separately)
    if request.args.get('mode') == 'start':
        return jsonify({'job_id': store_job_id})

    # Otherwise, stream events from the store (backward-compatible SSE response)
    def stream_from_store():
        past_events, live_queue = job_event_store.subscribe(store_job_id)
        if past_events is None:
            yield sse_message({'type': 'error', 'message': 'Job not found'})
            return

        # Replay events generated before we subscribed
        for event in past_events:
            yield sse_message(event)

        # Stream live events
        if live_queue is not None:
            while True:
                try:
                    event = live_queue.get(timeout=15)
                except queue.Empty:
                    yield sse_keepalive()
                    continue
                if event is None:  # sentinel = job done
                    break
                yield sse_message(event)

    resp = sse_response(stream_from_store())
    resp.headers['X-Job-Id'] = store_job_id
    return resp


@app.route('/api/jobs/active')
def active_jobs():
    """Return list of active/recent jobs for reconnection after page refresh."""
    jobs = job_event_store.get_active_jobs()
    return jsonify({'jobs': jobs})


@app.route('/api/jobs/<job_id>/stream')
def job_stream(job_id):
    """SSE endpoint that replays past events and streams live events for a job."""
    past_events, live_queue = job_event_store.subscribe(job_id)
    if past_events is None:
        return jsonify({'error': 'Job not found'}), 404

    def stream():
        # Replay all past events
        for event in past_events:
            yield sse_message(event)

        # Stream live events (if job still running)
        if live_queue is not None:
            while True:
                try:
                    event = live_queue.get(timeout=15)
                except queue.Empty:
                    yield sse_keepalive()
                    continue
                if event is None:
                    break
                yield sse_message(event)

    return sse_response(stream())


@app.route('/api/jobs/<job_id>/results')
def job_results(job_id):
    """Return all image results for a job (for non-SSE recovery)."""
    results = job_event_store.get_job_results(job_id)
    if results is None:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({'results': results})


@app.route('/api/get-rubric')
def get_rubric():
    """Get current rubric content for inline editing."""
    rubric_path = Path(__file__).parent / 'rubric.txt'
    try:
        with open(rubric_path, 'r') as f:
            rubric = f.read()
        return jsonify({'success': True, 'rubric': rubric})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-rubric', methods=['POST'])
def save_rubric():
    """Save rubric content and reload the refiner."""
    try:
        data = request.get_json()
        rubric = data.get('rubric', '')

        if not rubric.strip():
            return jsonify({'success': False, 'error': 'Rubric cannot be empty'}), 400

        rubric_path = Path(__file__).parent / 'rubric.txt'
        with open(rubric_path, 'w') as f:
            f.write(rubric)

        # Note: The refiner loads rubric in __init__, so next generation will use new rubric
        return jsonify({'success': True, 'message': 'Rubric saved! Will be used in next generation.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save-template-name', methods=['POST'])
def save_template_name():
    """Save the image prompt template name."""
    name = request.json.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'})
    prompt_manager.update_prompt('image_prompt_template_name', name, note='Template name update')
    return jsonify({'success': True})


@app.route('/api/reset-rubric', methods=['POST'])
def reset_rubric():
    """Reset rubric to default."""
    try:
        # Get default rubric from AgenticImageRefiner
        from lib.agentic_refiner import AgenticImageRefiner
        refiner = AgenticImageRefiner(settings)
        default_rubric = refiner._get_default_rubric()

        rubric_path = Path(__file__).parent / 'rubric.txt'
        with open(rubric_path, 'w') as f:
            f.write(default_rubric)

        return jsonify({'success': True, 'rubric': default_rubric})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/re-evaluate', methods=['POST'])
def re_evaluate():
    """Re-evaluate existing images with current rubric."""
    try:
        data = request.get_json()
        images = data.get('images', [])

        if not images:
            return jsonify({'success': False, 'error': 'No images provided'}), 400

        # Create new refiner with current rubric
        from lib.agentic_refiner import AgenticImageRefiner
        refiner = AgenticImageRefiner(settings)

        # Prepare images for batch evaluation
        images_data = []
        for img in images:
            images_data.append({
                'image_path': Path(settings.output_dir) / img['file_path'],
                'prompt_used': img['prompt_used'],
                'concept_name': img['concept_name'],
                'model': img['model']
            })

        # Evaluate with current rubric
        evaluations = refiner.evaluate_thumbnails_batch(images_data)

        # Calculate average change (comparing to frontend's existing scores)
        avg_change = sum(e['score'] for e in evaluations) / len(evaluations) if evaluations else 0

        return jsonify({
            'success': True,
            'results': evaluations,
            'avg_change': avg_change
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parallel-variations', methods=['POST'])
def parallel_variations():
    """
    Generate variations using multiple models IN PARALLEL.

    POST body:
    - favorite_id: ID of the favorite to base variations on
    - num_variations: How many variations per model
    - style: "similar", "explore", or "remix"
    - models: List of models to use (default: all)
    """
    data = request.json
    favorite_id = data.get('favorite_id')
    num_variations = int(data.get('num_variations', 3))
    variation_style = data.get('style', 'similar')
    selected_models = data.get('models', None)

    if not favorite_id:
        return jsonify({'success': False, 'error': 'No favorite_id provided'})

    favorites_mgr = FavoritesManager(settings)
    base_concept = favorites_mgr.get_favorite_for_variation(int(favorite_id))

    if not base_concept:
        return jsonify({'success': False, 'error': 'Favorite not found'})

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        generator = _make_generator()
        available_models = generator.get_available_models()

        models_to_use = selected_models if selected_models else available_models
        models_to_use = [m for m in models_to_use if m in available_models]

        yield sse_message({
            'type': 'parallel_start',
            'models': models_to_use,
            'base_concept': base_concept['concept_name'],
            'message': f'Generating {num_variations} variations each with {len(models_to_use)} models...'
        })

        # Step 1: Generate variation concepts (only once, shared across all models)
        yield sse_message({
            'type': 'progress',
            'phase': 'ideation',
            'message': 'Claude is generating variation concepts...'
        })

        try:
            concepts = ideator.generate_variations(
                base_concept=base_concept,
                num_variations=num_variations,
                variation_style=variation_style
            )
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Claude error: {str(e)}'})
            return

        if not concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated'})
            return

        yield sse_message({
            'type': 'progress',
            'phase': 'prompts',
            'message': f'Generating prompts for {len(concepts)} concepts...'
        })

        try:
            prompts_with_concepts = ideator.generate_prompts_for_concepts(concepts)
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Prompt error: {str(e)}'})
            return

        # Step 2: Generate images with each model IN PARALLEL
        total_images = len(prompts_with_concepts) * len(models_to_use)
        yield sse_message({
            'type': 'progress',
            'phase': 'generation',
            'message': f'Generating {total_images} images ({len(prompts_with_concepts)} concepts × {len(models_to_use)} models)...'
        })

        # Initialize model status
        for model in models_to_use:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'generating',
                'progress': 0,
                'total': len(prompts_with_concepts)
            })

        completed_per_model = {m: 0 for m in models_to_use}
        total_completed = 0

        def generate_one(model_name, prompt_data, index):
            """Generate a single image with a specific model."""
            result = generator.generate_with_model(model_name, prompt_data, f"variations/{model_name}")
            return model_name, prompt_data, result, index

        # Create all tasks
        tasks = []
        for idx, prompt_data in enumerate(prompts_with_concepts):
            for model in models_to_use:
                tasks.append((model, prompt_data, idx))

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
            futures = [executor.submit(generate_one, m, p, i) for m, p, i in tasks]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Generation stopped'})
                    return

                try:
                    model_name, prompt_data, result, idx = future.result()
                except Exception as e:
                    print(f"[FULL-PARALLEL] Future failed: {e}")
                    continue
                completed_per_model[model_name] += 1
                total_completed += 1

                # Update model progress
                yield sse_message({
                    'type': 'model_status',
                    'model': model_name,
                    'status': 'generating',
                    'progress': completed_per_model[model_name],
                    'total': len(prompts_with_concepts)
                })

                if result.get('success'):
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                    yield sse_message({
                        'type': 'thumbnail',
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': prompt_data.get('description', ''),
                        'based_on': base_concept['concept_name'],
                        'prompt': prompt_data.get('prompt', ''),
                        'model': model_name,
                        'progress': total_completed,
                        'total': total_images
                    })
                else:
                    yield sse_message({
                        'type': 'error',
                        'model': model_name,
                        'message': f'{model_name}: {result.get("error", "Unknown")[:50]}'
                    })

        # Mark all models complete
        for model in models_to_use:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'complete',
                'progress': completed_per_model[model],
                'total': len(prompts_with_concepts)
            })

        successful = sum(completed_per_model.values())
        yield sse_message({
            'type': 'parallel_complete',
            'total': total_images,
            'successful': successful,
            'message': f'Generated {successful} images across {len(models_to_use)} models'
        })

    return sse_response(generate_stream())


# ============================================================
# FULL PARALLEL - Multiple LLMs + Multiple Image Models
# ============================================================

@app.route('/api/available-llms')
def get_available_llms():
    """Get list of available LLM ideators."""
    multi_ideator = MultiLLMIdeator(settings)
    llms = multi_ideator.get_available_llms()

    llm_info = {
        "claude": {"name": "Claude", "description": "Anthropic's Claude with extended thinking"},
        "chatgpt": {"name": "ChatGPT", "description": "OpenAI GPT-4o"},
        "gemini": {"name": "Gemini", "description": "Google Gemini 2.0 Flash"},
    }

    return jsonify({
        "llms": [{"id": llm, **llm_info.get(llm, {"name": llm, "description": ""})} for llm in llms]
    })


@app.route('/api/full-parallel')
def full_parallel_generate():
    """
    MAXIMUM PARALLELIZATION: Multiple LLMs + Multiple Image Models

    This endpoint:
    1. Runs Claude, ChatGPT, and Gemini in PARALLEL to generate diverse concepts
    2. Generates prompts for all concepts
    3. Renders each concept with ALL selected image models in PARALLEL

    Query params:
    - titles: Newline-separated video titles
    - script: Optional video script
    - concepts_per_llm: Concepts each LLM should generate (default 7)
    - llms: Comma-separated LLMs to use (default: all available)
    - models: Comma-separated image models to use (default: all available)
    - use_favorites: Learn from favorites (default true)
    """
    err = _require_video_name()
    if err: return err
    titles_raw = request.args.get('titles', '')
    script = request.args.get('script', '')
    creative_direction = request.args.get('creative_direction', '')
    video_name = request.args.get('video_name', '')
    concepts_per_llm = int(request.args.get('concepts_per_llm', 7))
    llms_str = request.args.get('llms', '')
    models_str = request.args.get('models', '')
    use_favorites = request.args.get('use_favorites', 'true').lower() == 'true'

    titles = [t.strip() for t in titles_raw.split('\n') if t.strip()]

    if not titles:
        return Response(
            sse_message({'type': 'error', 'message': 'No titles provided'}),
            mimetype='text/event-stream'
        )

    def generate_stream():
        global _stop_generation
        _stop_generation = False

        # Initialize components
        multi_ideator = MultiLLMIdeator(settings)
        generator = _make_generator()
        favorites_mgr = FavoritesManager(settings)
        freshness = FreshnessTracker(settings)

        # Get available LLMs and models
        available_llms = multi_ideator.get_available_llms()
        available_models = generator.get_available_models()

        # Filter to selected ones
        selected_llms = [l.strip() for l in llms_str.split(',') if l.strip()] if llms_str else available_llms
        selected_llms = [l for l in selected_llms if l in available_llms]

        selected_models = [m.strip() for m in models_str.split(',') if m.strip()] if models_str else available_models
        selected_models = [m for m in selected_models if m in available_models]

        if not selected_llms:
            yield sse_message({'type': 'error', 'message': 'No LLMs available'})
            return

        if not selected_models:
            yield sse_message({'type': 'error', 'message': 'No image models available'})
            return

        # Get favorites context
        favorites_context = ""
        if use_favorites:
            favorites_context = favorites_mgr.get_favorites_summary_for_prompt(limit=5)

        # ========== PHASE 1: PARALLEL LLM IDEATION ==========
        yield sse_message({
            'type': 'phase',
            'phase': 'ideation',
            'llms': selected_llms,
            'message': f'Starting parallel ideation with {len(selected_llms)} LLMs...'
        })

        # Initialize LLM status
        for llm in selected_llms:
            yield sse_message({
                'type': 'llm_status',
                'llm': llm,
                'status': 'Starting...'
            })

        # Generate concepts with all LLMs in parallel
        llm_results = {}

        def ideate_with_llm(llm_name):
            try:
                concepts = multi_ideator.generate_with_single_llm(
                    llm_name=llm_name,
                    titles=titles,
                    used_ideas=freshness.get_summary_list(),
                    script=script,
                    favorites_context=favorites_context,
                    num_concepts=concepts_per_llm
                )
                return llm_name, concepts, None
            except Exception as e:
                return llm_name, [], str(e)

        with ThreadPoolExecutor(max_workers=len(selected_llms)) as executor:
            futures = [executor.submit(ideate_with_llm, llm) for llm in selected_llms]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Stopped during ideation'})
                    return

                try:
                    llm_name, concepts, error = future.result()
                    if error:
                        yield sse_message({
                            'type': 'llm_error',
                            'llm': llm_name,
                            'error': error[:200],
                            'message': f'{llm_name}: Error - {error[:100]}'
                        })
                        concepts = []
                    llm_results[llm_name] = concepts

                    yield sse_message({
                        'type': 'llm_complete',
                        'llm': llm_name,
                        'count': len(concepts),
                        'message': f'{llm_name}: Generated {len(concepts)} concepts'
                    })
                except Exception as e:
                    yield sse_message({
                        'type': 'llm_error',
                        'llm': 'unknown',
                        'error': str(e)[:200],
                        'message': f'Ideation error: {str(e)[:100]}'
                    })

        # Combine all concepts
        all_concepts = []
        for llm, concepts in llm_results.items():
            all_concepts.extend(concepts)

        if not all_concepts:
            yield sse_message({'type': 'error', 'message': 'No concepts generated by any LLM'})
            return

        yield sse_message({
            'type': 'ideation_complete',
            'total_concepts': len(all_concepts),
            'by_llm': {llm: len(c) for llm, c in llm_results.items()},
            'message': f'Got {len(all_concepts)} total concepts from {len(selected_llms)} LLMs'
        })

        # ========== PHASE 2: PROMPT GENERATION ==========
        yield sse_message({
            'type': 'phase',
            'phase': 'prompts',
            'message': 'Generating image prompts for all concepts...'
        })

        # Use Claude for prompt generation (best at following the prompting guide)
        ideator = ClaudeIdeator(settings, prompt_manager=prompt_manager)
        try:
            prompts_with_concepts = ideator.generate_prompts_for_concepts(all_concepts)
        except Exception as e:
            yield sse_message({'type': 'error', 'message': f'Prompt generation failed: {str(e)}'})
            return

        yield sse_message({
            'type': 'prompts_complete',
            'count': len(prompts_with_concepts),
            'message': f'Generated {len(prompts_with_concepts)} prompts'
        })

        # ========== PHASE 3: PARALLEL IMAGE GENERATION ==========
        total_images = len(prompts_with_concepts) * len(selected_models)

        yield sse_message({
            'type': 'phase',
            'phase': 'generation',
            'models': selected_models,
            'total_images': total_images,
            'message': f'Generating {total_images} images ({len(prompts_with_concepts)} concepts × {len(selected_models)} models)...'
        })

        # Initialize model status
        for model in selected_models:
            yield sse_message({
                'type': 'model_status',
                'model': model,
                'status': 'Starting...',
                'progress': 0,
                'total': len(prompts_with_concepts)
            })

        completed_per_model = {m: 0 for m in selected_models}
        total_completed = 0
        batch_id = f"fullparallel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def generate_one(model_name, prompt_data, idx):
            result = generator.generate_with_model(model_name, prompt_data, f"{batch_id}/{model_name}")
            return model_name, prompt_data, result, idx

        # Create all tasks
        tasks = []
        for idx, prompt_data in enumerate(prompts_with_concepts):
            for model in selected_models:
                tasks.append((model, prompt_data, idx))

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=min(12, len(tasks))) as executor:
            futures = [executor.submit(generate_one, m, p, i) for m, p, i in tasks]

            for future in as_completed(futures):
                if _stop_generation:
                    yield sse_message({'type': 'stopped', 'message': 'Stopped during generation'})
                    return

                try:
                    model_name, prompt_data, result, idx = future.result()
                except Exception as e:
                    print(f"[FULL-PARALLEL-GEN] Future failed: {e}")
                    continue
                completed_per_model[model_name] += 1
                total_completed += 1

                if result.get('success'):
                    file_path = result['file_path'].replace(str(settings.output_dir) + '/', '')
                    freshness.add_used_idea(prompt_data)

                    # Auto-composite logos
                    _apply_logos_to_image(file_path, titles_raw, creative_direction, prompt_data.get('concept_name', ''))

                    template_label = creative_direction.split(' — ')[0].strip() if creative_direction else ''
                    thumbnail_data = {
                        'type': 'model_thumbnail',
                        'model': model_name,
                        'file_path': file_path,
                        'concept_name': prompt_data.get('concept_name', ''),
                        'concept_summary': prompt_data.get('description', ''),
                        'category': prompt_data.get('category', ''),
                        'prompt': prompt_data.get('prompt', ''),
                        'source_llm': prompt_data.get('source_llm', 'unknown'),
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts),
                        'overall_current': total_completed,
                        'overall_total': total_images,
                        'video_name': video_name,
                        'template_name': prompt_manager.get_prompt('image_prompt_template_name') or 'Unnamed',
                        'template': template_label,
                    }

                    # Save to history
                    job_manager.add_result(batch_id, thumbnail_data)

                    yield sse_message(thumbnail_data)

                    yield sse_message({
                        'type': 'model_progress',
                        'model': model_name,
                        'current': completed_per_model[model_name],
                        'total': len(prompts_with_concepts)
                    })
                else:
                    yield sse_message({
                        'type': 'model_error',
                        'model': model_name,
                        'error': result.get('error', 'Unknown')[:100]
                    })

        # Mark all models complete
        for model in selected_models:
            yield sse_message({
                'type': 'model_complete',
                'model': model,
                'count': completed_per_model[model]
            })

        yield sse_message({
            'type': 'full_parallel_complete',
            'total_generated': total_completed,
            'llms_used': selected_llms,
            'models_used': selected_models,
            'concepts_generated': len(all_concepts),
            'message': f'Generated {total_completed} images from {len(all_concepts)} concepts across {len(selected_llms)} LLMs and {len(selected_models)} image models'
        })

    return sse_response(generate_stream())


if __name__ == '__main__':
    print("=" * 60)
    print("Thumbnail Generator v2")
    print("=" * 60)
    print(f"Output directory: {settings.output_dir}")
    print(f"Data directory: {settings.data_dir}")
    print()
    print("Features:")
    print("  1. Favorites system - Mark winning thumbnails")
    print("  2. Variation generation - Generate more like your favorites")
    print("  3. Multi-model support - Gemini, Flux, SDXL, Ideogram")
    print("  4. Learning from success - Uses favorites to improve generation")
    print()

    # On startup: protect any existing favorites whose images are still on disk
    _protect_existing_favorites()

    # Use PORT from environment (Railway/production) or default to 5050 (local)
    port = int(os.getenv('PORT', 5050))
    host = '0.0.0.0' if os.getenv('PORT') else '127.0.0.1'

    print(f"Open http://localhost:{port} to start")
    print("=" * 60)
    is_production = bool(os.getenv('PORT'))
    app.run(debug=not is_production, host=host, port=port)
