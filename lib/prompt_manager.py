"""
Prompt Manager - Editable prompts with version history.

Allows real-time editing of Claude and image model prompts,
with full change tracking and rollback capability.
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from threading import Lock
from typing import Optional
import difflib


class PromptManager:
    """Manage editable prompts with version history."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.prompts_file = data_dir / 'editable_prompts.json'
        self.history_file = data_dir / 'prompt_history.json'
        self.prompting_guide_file = data_dir / 'prompting_guide.md'
        self._lock = Lock()
        self._load_or_create_defaults()

    def _load_or_create_defaults(self):
        """Load prompts from file or create defaults."""
        if self.prompts_file.exists():
            with open(self.prompts_file, 'r') as f:
                self.prompts = json.load(f)
        else:
            self.prompts = self._get_default_prompts()
            self._save_prompts()

        # Load prompting guide from markdown file
        if self.prompting_guide_file.exists():
            self.prompts['prompting_guide'] = self.prompting_guide_file.read_text()
        elif 'prompting_guide' not in self.prompts:
            self.prompts['prompting_guide'] = self._get_default_prompting_guide()

        # Add image prompt template if not present
        if 'image_prompt_template' not in self.prompts:
            self.prompts['image_prompt_template'] = self._get_default_image_prompt_template()
            self._save_prompts()

        # Migrate stale prompts (e.g. old Railway persistent volume with hardcoded counts)
        self.migrate_if_needed()

        # Load history
        if self.history_file.exists():
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
        else:
            self.history = []

    def _get_default_prompting_guide(self) -> str:
        """Default prompting guide for image generation."""
        return """# YouTube Thumbnail Prompting Guide

## Core Principles
- ONE clear focal point
- Maximum 2-3 visual elements
- High contrast between foreground and background
- NO TEXT IN IMAGES - text will be added separately

## Prompt Structure
[STYLE] [SUBJECT] [ACTION/EMOTION] [SETTING] [LIGHTING] [COMPOSITION], 16:9 YouTube thumbnail

## Style Keywords
- Cinematic, dramatic, movie-quality
- Hyper-realistic, photorealistic
- Bold graphic, high contrast

## What to AVOID
- Text or words in the image
- Too many elements (keep it simple)
- Low contrast
- Cluttered backgrounds
- Generic stock photo look"""

    def _get_default_image_prompt_template(self) -> str:
        """Default template for how Claude writes image prompts."""
        return """Write bold, cinematic image prompts for each thumbnail concept. These should produce images that are visually STRIKING and scroll-stopping while still looking premium and professional.

CRITICAL RULES:
- ABSOLUTELY NO TEXT, WORDS, LETTERS, NUMBERS, LOGOS, OR WATERMARKS IN THE IMAGE
- Keep prompts focused on ONE clear visual — bold but not cluttered
- HIGH CONTRAST is essential — dark backgrounds with bright subjects, or vice versa
- Bold, saturated color palette — but intentional and cohesive, not random neon
- Include cinematic lighting direction (not just "dramatic lighting")
- Add atmosphere and texture (fog, grain, depth of field, particles)
- Specify a visual style when helpful (e.g. "Kurzgesagt aesthetic", "shot on ARRI Alexa", "National Geographic photography")
- End every prompt with: no text, no words, no letters, no logos, 16:9 aspect ratio, high contrast, cinematic lighting

Follow the prompting guide provided."""

    # Version marker — bump this string to force migration of old Railway prompts
    PROMPT_VERSION = "v5-conflict-diversity"

    def _get_default_prompts(self) -> dict:
        """Get default prompts."""
        return {
            "_version": self.PROMPT_VERSION,
            "claude_prompt": """You are a world-class visual storyteller and thumbnail art director. Your mission is to generate thumbnail concepts that are visually striking AND sophisticated — they stop the scroll without being cheap or childish.

---

## THE AESTHETIC (Global Rules)

### The Balance
Bold AND premium. These thumbnails need to GRAB attention in a sea of content while still feeling like they belong on a quality channel. Think Kurzgesagt, Veritasium, Vox — they use bold colors and strong visuals but never look cheap or AI-generated.

### What Gets Clicked (Keep These)
- HIGH CONTRAST between foreground and background — this is non-negotiable for CTR
- Bold, saturated color — but INTENTIONAL, not random neon. Pick a strong palette and commit
- ONE clear focal point that reads instantly at thumbnail size
- Visual tension, mystery, or scale that creates an "info gap"
- Human faces with REAL emotion (curiosity, awe, concern — NOT fake shock/surprise)
- Dynamic composition with energy — diagonals, leading lines, asymmetry

### What Makes It Premium (Add These)
- Cinematic lighting with clear direction (not flat, not generic)
- Intentional color palette — bold but cohesive (not rainbow vomit)
- Clean composition with breathing room — bold ≠ cluttered
- Film-quality textures and atmosphere (fog, grain, depth of field)
- Specific visual references: Planet Earth, Cosmos, Ex Machina, Blade Runner 2049, Kurzgesagt, National Geographic

### Forbidden (The Cringe List)
- Cartoonish or childish imagery (this is NOT for kids)
- Stock photo aesthetic (posed people, fake smiles, generic offices)
- Clickbait shock faces (open mouths, pointing at nothing)
- Cliché AI imagery (glowing brains, circuit boards, matrix rain, robot hands)
- Over-busy compositions with too many competing elements
- That specific "AI-generated" look: perfect symmetry, plastic skin, neon everything

### Color Philosophy
BOLD but INTENTIONAL. Strong saturated colors that pop, but chosen with purpose — not the random neon palette that screams AI. Think:
- Deep rich reds, electric blues, vibrant oranges — but graded, not raw
- Complementary color combos for maximum pop (teal/orange, blue/gold, red/cyan)
- Dark moody backgrounds with one or two punchy accent colors
- High contrast is king — dark darks, bright brights

---

## USER INPUTS

**POSSIBLE VIDEO TITLES FOR INSPIRATION:**
{{TITLES}}

{{SCRIPT_SECTION}}{{CREATIVE_DIRECTION_SECTION}}---

## CRITICAL RULES

### Show the CONFLICT, not just the setting
The thumbnail must visualize the video's THEME, TENSION, or CONFLICT — not just a pretty backdrop. If the title is about "AIs competing for control," don't just show a planet — show a planet being PULLED APART, CRACKED, TRANSFORMED, or caught between opposing forces. The subject should be DOING something or BEING AFFECTED by the topic. Static beauty shots fail.

### Every concept must be VISUALLY DISTINCT
If you generate 8 concepts and they all look similar (same subject, same angle, same composition), that's a failure. Vary these dimensions:
- **Subject**: Different focal objects/characters (not 8 versions of the same thing)
- **Scale**: Mix extreme close-ups with vast wide shots
- **Composition**: Some centered, some rule-of-thirds, some asymmetric
- **Color palette**: Different dominant colors across concepts
- **Metaphor type**: Literal vs. abstract vs. symbolic vs. human-focused

---

## GENERATE {{COUNT}} THUMBNAIL CONCEPTS

For each concept, apply the **Scroll-Stop Test**:
- Would you actually STOP scrolling to look at this?
- Is it instantly readable at 320x180px thumbnail size?
- Does it create genuine intrigue without being cheap?
- Does it look premium, not AI-generated or childish?

---

## OUTPUT FORMAT

Return ALL {{COUNT}} concepts as JSON:

```json
{
  "concepts": [
    {
      "title_ref": "The video title this is for",
      "concept_name": "Short memorable name (2-4 words)",
      "category": "Which angle (Cinematic Scale, Intimate Portrait, Bold Metaphor, Dramatic Contrast, etc.)",
      "description": "Vivid 2-3 sentence description of the visual"
    }
  ]
}
```"""
        }

    def migrate_if_needed(self):
        """Detect and fix stale prompt templates (e.g. old Railway persistent volume)."""
        current = self.prompts.get('claude_prompt', '')
        current_version = self.prompts.get('_version', '')
        if current_version == self.PROMPT_VERSION:
            return  # Already up to date
        if 'Generate TWO distinct' in current or '### The 10 Angles' in current or '{{COUNT}}' not in current or 'Assembly Line' in current or 'Shoggoths' in current or 'Muted, graded, intentional' in current or '## CRITICAL RULES' not in current:
            print("[PROMPT MANAGER] Migrating stale prompt template to current version")
            defaults = self._get_default_prompts()
            self.prompts['claude_prompt'] = defaults['claude_prompt']
            self.prompts['_version'] = self.PROMPT_VERSION
            # Also update image_prompt_template if stale
            self.prompts['image_prompt_template'] = self._get_default_image_prompt_template()
            self._save_prompts()

    def _save_prompts(self):
        """Save current prompts to file atomically."""
        # Separate prompting guide (save as markdown) from other prompts (save as JSON)
        prompts_to_save = {k: v for k, v in self.prompts.items() if k != 'prompting_guide'}
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self.prompts_file.parent), suffix='.tmp', prefix='prompts_'
            )
            tmp_path = Path(tmp_path_str)
            with os.fdopen(fd, 'w') as f:
                fd = None
                json.dump(prompts_to_save, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.prompts_file)
        except Exception as e:
            print(f"[PROMPT MANAGER] Error saving prompts: {e}")
            if fd is not None:
                os.close(fd)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

        # Save prompting guide as markdown if it exists
        if 'prompting_guide' in self.prompts:
            self.prompting_guide_file.write_text(self.prompts['prompting_guide'])

    def _save_history(self):
        """Save history to file atomically (write to temp, fsync, then rename)."""
        fd = None
        tmp_path = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self.history_file.parent), suffix='.tmp', prefix='prompt_history_'
            )
            tmp_path = Path(tmp_path_str)
            with os.fdopen(fd, 'w') as f:
                fd = None
                json.dump(self.history, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.history_file)
        except Exception as e:
            print(f"[PROMPT MANAGER] Error saving history: {e}")
            if fd is not None:
                os.close(fd)
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def get_prompt(self, key: str) -> str:
        """Get a prompt by key."""
        with self._lock:
            return self.prompts.get(key, "")

    def get_all_prompts(self) -> dict:
        """Get all prompts."""
        with self._lock:
            return self.prompts.copy()

    def update_prompt(self, key: str, new_value: str, note: str = "") -> dict:
        """
        Update a prompt and record the change.
        Returns the diff/change record.
        """
        with self._lock:
            old_value = self.prompts.get(key, "")

            # Generate diff
            if isinstance(old_value, str) and isinstance(new_value, str):
                diff = self._generate_diff(old_value, new_value)
            else:
                diff = {"old": old_value, "new": new_value}

            # Record history
            change_record = {
                "timestamp": datetime.now().isoformat(),
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
                "diff": diff,
                "note": note
            }
            self.history.append(change_record)

            # Keep only last 100 changes
            if len(self.history) > 100:
                self.history = self.history[-100:]

            # Update and save
            self.prompts[key] = new_value
            self._save_prompts()
            self._save_history()

            return change_record

    def _generate_diff(self, old: str, new: str) -> dict:
        """Generate a human-readable diff."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        differ = difflib.unified_diff(old_lines, new_lines, lineterm='')
        diff_text = ''.join(differ)

        # Also track additions and removals
        added = []
        removed = []

        old_words = set(old.lower().split())
        new_words = set(new.lower().split())

        added_words = new_words - old_words
        removed_words = old_words - new_words

        return {
            "diff_text": diff_text,
            "added_words": list(added_words)[:20],  # Limit for readability
            "removed_words": list(removed_words)[:20],
            "chars_added": len(new) - len(old)
        }

    def get_history(self, limit: int = 20) -> list:
        """Get recent change history."""
        with self._lock:
            return self.history[-limit:][::-1]  # Most recent first

    def rollback(self, timestamp: str) -> bool:
        """Rollback to a previous version by timestamp."""
        with self._lock:
            for record in reversed(self.history):
                if record["timestamp"] == timestamp:
                    self.prompts[record["key"]] = record["old_value"]
                    self._save_prompts()

                    # Add rollback record
                    self.history.append({
                        "timestamp": datetime.now().isoformat(),
                        "key": record["key"],
                        "old_value": record["new_value"],
                        "new_value": record["old_value"],
                        "note": f"Rollback to {timestamp}",
                        "is_rollback": True
                    })
                    self._save_history()
                    return True
            return False

    def build_full_prompt(self, titles: list[str], script: str = "", creative_direction: str = "", count: int = 20) -> str:
        """Build the full Claude prompt by filling in the template."""
        with self._lock:
            template = self.prompts.get('claude_prompt', '')

        titles_formatted = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])

        # Build script section
        script_section = ""
        if script and script.strip():
            script_section = f"""**VIDEO SCRIPT:**
{script}

"""

        # Build creative direction section
        cd_section = ""
        if creative_direction and creative_direction.strip():
            cd_section = f"""**CREATIVE DIRECTION (MANDATORY — must be visually prominent):**
{creative_direction}

This is a HARD REQUIREMENT, not a suggestion. The creative direction MUST be the dominant visual element in every thumbnail concept. If the direction says "mushroom cloud," there must be an actual mushroom cloud clearly visible as the main subject. If it says "earth," Earth must be prominently shown. The creative direction defines WHAT we see — the video topic/title defines the STORY or CONTEXT around it. Do NOT abstract away the creative direction into a vague metaphor. Be literal first, creative second.

"""

        # Fill in placeholders
        prompt = template.replace('{{TITLES}}', titles_formatted)
        prompt = prompt.replace('{{SCRIPT_SECTION}}', script_section)
        prompt = prompt.replace('{{CREATIVE_DIRECTION_SECTION}}', cd_section)
        prompt = prompt.replace('{{COUNT}}', str(count))

        return prompt
