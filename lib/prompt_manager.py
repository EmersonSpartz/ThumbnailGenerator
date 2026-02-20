"""
Prompt Manager - Editable prompts with version history.

Allows real-time editing of Claude and image model prompts,
with full change tracking and rollback capability.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import difflib


class PromptManager:
    """Manage editable prompts with version history."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.prompts_file = data_dir / 'editable_prompts.json'
        self.history_file = data_dir / 'prompt_history.json'
        self.prompting_guide_file = data_dir / 'prompting_guide.md'
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
        return """Write NanoBanana Pro prompts for each thumbnail concept.

CRITICAL RULES:
- NO TEXT IN THE IMAGE - never include text, words, letters, or numbers in the prompt
- Keep prompts focused on ONE clear visual
- Describe the scene cinematically
- Include lighting and composition details
- End with: 16:9 YouTube thumbnail, high contrast

Follow the prompting guide provided."""

    # Version marker — bump this string to force migration of old Railway prompts
    PROMPT_VERSION = "v2-count-controlled"

    def _get_default_prompts(self) -> dict:
        """Get default prompts."""
        return {
            "_version": self.PROMPT_VERSION,
            "claude_prompt": """You are The Assembly Line, a master AI Art Director and high-volume production engine. Your mission is to generate a massive, diverse portfolio of high-CTR thumbnail concepts.

---

## THE ARTISTIC MANDATE (Global Rules)

### Visual Vocabulary
You are encouraged to build concepts using visually powerful nouns, e.g.: Massive Robots, Uncanny Humanoids, Terrifying Monsters, Alien Invasion, Shoggoths, Skulls, Chains, Cages, Explosions, Swarms, Alarm-Bell Red, Danger, viral outbreak, Orwellian surveillance

### Forbidden Tropes
You are forbidden from using visually boring or ambiguous imagery: circuit boards, wires, abstract data streams, glowing brains, server racks, generic office supplies, flowcharts, diagrams, infographics, scientists in lab coats, social media logos, stock photo aesthetics.

---

## USER INPUTS

**POSSIBLE VIDEO TITLES FOR INSPIRATION:**
{{TITLES}}

{{SCRIPT_SECTION}}{{CREATIVE_DIRECTION_SECTION}}---

## GENERATE {{COUNT}} THUMBNAIL CONCEPTS

For each concept, apply the **Squint Test**:
- Is it instantly understandable in under 1 second?
- Does it have a strong, clear silhouette? Is it SIMPLE?
- Does it evoke a powerful, primal emotion?

---

## OUTPUT FORMAT

Return ALL {{COUNT}} concepts as JSON:

```json
{
  "concepts": [
    {
      "title_ref": "The video title this is for",
      "concept_name": "Short memorable name (2-4 words)",
      "category": "Which angle (Human Reaction, Power Dynamic, etc.)",
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
        if 'Generate TWO distinct' in current or '### The 10 Angles' in current or '{{COUNT}}' not in current:
            print("[PROMPT MANAGER] Migrating stale prompt template to current version")
            defaults = self._get_default_prompts()
            self.prompts['claude_prompt'] = defaults['claude_prompt']
            self.prompts['_version'] = self.PROMPT_VERSION
            self._save_prompts()

    def _save_prompts(self):
        """Save current prompts to file."""
        # Separate prompting guide (save as markdown) from other prompts (save as JSON)
        prompts_to_save = {k: v for k, v in self.prompts.items() if k != 'prompting_guide'}
        with open(self.prompts_file, 'w') as f:
            json.dump(prompts_to_save, f, indent=2)

        # Save prompting guide as markdown if it exists
        if 'prompting_guide' in self.prompts:
            self.prompting_guide_file.write_text(self.prompts['prompting_guide'])

    def _save_history(self):
        """Save history to file."""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def get_prompt(self, key: str) -> str:
        """Get a prompt by key."""
        return self.prompts.get(key, "")

    def get_all_prompts(self) -> dict:
        """Get all prompts."""
        return self.prompts.copy()

    def update_prompt(self, key: str, new_value: str, note: str = "") -> dict:
        """
        Update a prompt and record the change.
        Returns the diff/change record.
        """
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
        return self.history[-limit:][::-1]  # Most recent first

    def rollback(self, timestamp: str) -> bool:
        """Rollback to a previous version by timestamp."""
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
            cd_section = f"""**CREATIVE DIRECTION (IMPORTANT - follow this guidance):**
{creative_direction}

Incorporate this creative direction into ALL concepts. This is the user's vision for the visual style.

"""

        # Get the template and fill in placeholders
        template = self.prompts.get('claude_prompt', '')

        prompt = template.replace('{{TITLES}}', titles_formatted)
        prompt = prompt.replace('{{SCRIPT_SECTION}}', script_section)
        prompt = prompt.replace('{{CREATIVE_DIRECTION_SECTION}}', cd_section)
        prompt = prompt.replace('{{COUNT}}', str(count))

        return prompt
