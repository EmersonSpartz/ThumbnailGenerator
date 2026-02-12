#!/usr/bin/env python3
"""
Generate fresh context for Claude sessions by reading current codebase state.
Run: python context.py

Output: Markdown summary of current system state (models, API keys, recent changes)
"""

import re
import os
from pathlib import Path
from datetime import datetime


def get_active_generators():
    """Extract active generators from image_generator.py MultiModelGenerator class."""
    gen_file = Path("lib/image_generator.py")
    if not gen_file.exists():
        return []

    content = gen_file.read_text()

    # Find MultiModelGenerator.__init__ section
    match = re.search(r'class MultiModelGenerator:.*?def __init__\(self.*?\n(.*?)(?=\n    def )',
                     content, re.DOTALL)
    if not match:
        return []

    init_code = match.group(1)

    # Extract generator registrations
    generators = []
    for line in init_code.split('\n'):
        # Look for self.generators["name"] =
        if 'self.generators[' in line and '=' in line and not line.strip().startswith('#'):
            match = re.search(r'self\.generators\["([^"]+)"\]\s*=\s*(\w+)', line)
            if match:
                name, class_name = match.groups()
                generators.append({"id": name, "class": class_name})

    return generators


def get_env_keys():
    """Extract configured API keys from .env."""
    env_file = Path(".env")
    if not env_file.exists():
        return []

    keys = []
    for line in env_file.read_text().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            if value and value != '':
                keys.append({"key": key, "set": True})

    return keys


def get_frontend_models():
    """Extract model checkboxes from index.html to verify frontend/backend sync."""
    html_file = Path("templates/index.html")
    if not html_file.exists():
        return []

    content = html_file.read_text()

    # Find shootout checkboxes section
    match = re.search(r'id="shootout-model-checkboxes"[^>]*>(.*?)</div>\s*</div>',
                     content, re.DOTALL)
    if not match:
        return []

    section = match.group(1)

    # Extract checkbox values
    models = re.findall(r'<input[^>]*value="([^"]+)"', section)
    return models


def get_recent_commits():
    """Get last 5 git commits if in a repo."""
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-5'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip().split('\n')
    except:
        pass
    return []


def main():
    """Generate context markdown."""
    print("# Thumbnail Generator v2 - Current State")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print("## Quick Start")
    print("```bash")
    print("cd /Users/emersonspartz/Downloads/Claude/thumbnail_generator_v2")
    print("source venv/bin/activate")
    print("python app.py  # localhost:5050")
    print("```\n")

    print("## Active Image Generators (Backend)")
    generators = get_active_generators()
    if generators:
        for gen in generators:
            print(f"- **{gen['id']}** ({gen['class']})")
    else:
        print("_Could not detect generators_")
    print()

    print("## Frontend Models (Checkboxes)")
    frontend = get_frontend_models()
    if frontend:
        for model in frontend:
            print(f"- {model}")
    else:
        print("_Could not detect frontend models_")
    print()

    print("## Configured API Keys")
    keys = get_env_keys()
    if keys:
        for key_info in keys:
            print(f"- ✓ {key_info['key']}")
    else:
        print("_No API keys configured_")
    print()

    print("## Recent Commits")
    commits = get_recent_commits()
    if commits:
        for commit in commits:
            print(f"- {commit}")
    else:
        print("_Not a git repo or no commits_")
    print()

    print("## Architecture Quick Reference")
    print("- **Backend**: Flask on port 5050 with SSE streaming")
    print("- **Image generators**: Inherit from `ImageGeneratorBase` in `lib/image_generator.py`")
    print("- **Frontend**: Single-page app in `templates/index.html` with 4 checkbox sections")
    print("- **Method signature**: `generate(prompt_data: dict, batch_id: str) -> dict`")
    print("- **Adding models**: Update MultiModelGenerator, app.py model_info, all 4 frontend sections, .env")
    print()

    print("## Key Files")
    print("- `app.py` - Flask server")
    print("- `lib/image_generator.py` - All generator classes (~900 lines)")
    print("- `lib/ideator.py` - Claude/Gemini ideation")
    print("- `templates/index.html` - Frontend UI (~3200 lines)")
    print("- `.env` - API keys (NEVER commit)")
    print()

    print("---")
    print("_Context auto-generated from codebase. Always accurate._")


if __name__ == "__main__":
    main()
