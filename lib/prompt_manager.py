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

        # Add image prompt template name if not present
        if 'image_prompt_template_name' not in self.prompts:
            self.prompts['image_prompt_template_name'] = 'Default'
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
        return """# Species Thumbnail Prompting Guide

## Brand Identity
Species is a premium AI/tech YouTube channel with a distinct OMINOUS SCI-FI aesthetic.
Primary color: Shoggoth Red (#E20020) — alarm bell red. ALWAYS present as accent.
Background: Always dark/black. Never bright, never cheerful.
Mood: Ominous, technological, documentary-grade, slightly dystopian.

## Core Principles
- ONE clear focal point
- Maximum 2-3 visual elements
- High contrast: dark backgrounds with bright subjects
- NO TEXT IN IMAGES - text will be added separately
- RED accent lighting or glow in every image

## Prompt Structure
[STYLE] [SUBJECT] [ACTION/EMOTION] [DARK SETTING] [RED-TINTED LIGHTING] [COMPOSITION], dark ominous mood, red accent lighting, 16:9 YouTube thumbnail

## Style Keywords
- Cinematic, dramatic, ominous, dystopian
- Graphic design, photorealistic cinematic, conceptual, symbolic
- CRT glow, dithered texture, film grain, chromatic aberration
- Dark room, red emergency lighting, sci-fi atmosphere
- NEVER photorealistic stock photos — ALWAYS bold graphic/symbolic compositions

## Species Color Palette
- Shoggoth Red #E20020 (primary accent)
- Glitch Cyan #22E2FF (tech/data)
- Glitch Magenta #F732EF (digital glitch)
- Progress Blue #2015ED (timelines)
- Tension Orange #FBB500 (warnings)
- Datacenter Green #4DF000 (data/terminal)

## What to AVOID
- Text or words in the image
- Bright, cheerful, or colorful backgrounds
- Generic stock photo look — NO realistic office scenes, people at computers, mundane environments
- Clickbait shock faces
- Cliché AI imagery (glowing brains, circuit boards, matrix rain)
- Photorealistic scenes of everyday life — thumbnails should be BOLD and SYMBOLIC, not literal

## What Species Thumbnails ACTUALLY Look Like (study these)
- A melting/dripping OpenAI logo against dark textured background with red glow
- A graph/chart with dramatic red crash line and CRT texture overlay
- A giant mechanical eye with a silhouette walking beneath it
- A red Minecraft figure standing alone on a red-lit platform with dark cityscape
- A tentacle monster erupting from an OpenAI logo
- Bold iconic SYMBOLS, not realistic scenes"""

    def _get_default_image_prompt_template(self) -> str:
        """Default template for how Claude writes image prompts."""
        return """Write bold, SYMBOLIC image prompts for each thumbnail concept. Species thumbnails look like graphic design/photorealistic cinematic — NOT photographs, NOT nature scenes, NOT landscapes.

THE SPECIES LOOK (study real examples):
- ONE iconic symbolic element against a dark textured background
- Red (#E20020) is the dominant accent — red glow, red backlighting, red elements everywhere
- Compositions are CONCEPTUAL and METAPHORICAL — represent ideas with bold symbols, not literal scenes
- Think: a cracked planet, a melting logo, a glowing red eye, chess pieces on fire, a red string connecting objects
- The style is closer to movie poster / photorealistic cinematic than photography
- Accent colors: cyan (#22E2FF) for tech/glitch, magenta (#F732EF) for digital, orange (#FBB500) for tension
- EVERYTHING should feel TECHNOLOGICAL, DIGITAL, SCI-FI — even natural metaphors (iceberg, ocean, road) must be rendered as digital/glitch/holographic versions, never photorealistic nature

ABSOLUTE RULES:
- NO TEXT, WORDS, LETTERS, NUMBERS, LOGOS, OR WATERMARKS
- NEVER generate realistic nature scenes — no photorealistic forests, mountains, oceans, landscapes, sunsets, waterfalls, meadows, or outdoor scenery
- NEVER generate realistic office scenes, people at desks, mundane everyday settings
- NEVER generate generic stock-photo-style compositions
- If a concept involves a natural element (iceberg, road, tree, etc.), render it as a DIGITAL/HOLOGRAPHIC/GLITCH version — glowing wireframe, made of code, pixelated, circuit-board texture — NOT a photograph of the real thing
- ONE clear visual idea per image — bold, minimal, iconic
- Dark background with TEXTURE (grain, noise, subtle pattern) — not pure black void
- High contrast: dark background, bright/glowing subject
- End every prompt with: no text, no words, no letters, 16:9 aspect ratio, dark textured background, bold minimal composition, ominous red accent lighting, photorealistic rendering, NOT cartoon, NOT comic book, NOT cel-shaded, NOT animated

Follow the prompting guide provided."""

    # Version marker — bump this string to force migration of old Railway prompts
    PROMPT_VERSION = "v8-layouts"

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
- Artistic face compositions ONLY if art-directed (dramatic lighting, partial face, symbolic overlay) — NO generic face close-ups or stock-photo-style emotion shots
- Dynamic composition with energy — diagonals, leading lines, asymmetry

### What Makes It Premium (Add These)
- Cinematic lighting with clear direction (not flat, not generic)
- Intentional color palette — bold but cohesive (not rainbow vomit)
- Clean composition with breathing room — bold ≠ cluttered
- Film-quality textures and atmosphere (fog, grain, depth of field)
- Specific visual references: Planet Earth, Cosmos, Ex Machina, Blade Runner 2049, Kurzgesagt, National Geographic

### Forbidden (The Cringe List)
- Cartoonish or childish imagery (this is NOT for kids)
- Stock photo aesthetic (posed people, fake smiles, generic offices, people at desks, mundane real-world scenes)
- Clickbait shock faces (open mouths, pointing at nothing)
- Cliché AI imagery (glowing brains, circuit boards, matrix rain, robot hands)
- Over-busy compositions with too many competing elements
- That specific "AI-generated" look: perfect symmetry, plastic skin, neon everything
- Literal/photorealistic interpretations — Species uses SYMBOLIC, METAPHORICAL visuals (a melting logo = AI failing, a cracked chess piece = AI strategy breaking down, a red eye = AI surveillance)

### Color Philosophy — SPECIES BRAND PALETTE
The Species channel has a distinct visual identity. USE THESE COLORS:
- **PRIMARY: Shoggoth Red (#E20020)** — alarm bell red. Use as the dominant accent color in most thumbnails. Red glows, red lighting, red highlights.
- **Glitch Cyan (#22E2FF)** — electric cyan for tech/data/glitch effects
- **Glitch Magenta (#F732EF)** — for glitch/digital corruption effects
- **Progress Blue (#2015ED)** — for timelines, progress, graphs
- **Tension Orange (#FBB500)** — for warning/tension moments
- **Datacenter Green (#4DF000)** — for data/terminal/tech elements

ALWAYS use dark/black backgrounds with these accent colors. The Species look is OMINOUS and SCI-FI — think dark room with red emergency lighting, not bright and cheerful. Complementary combos: red/cyan, red/blue, cyan/magenta.

### Visual Texture & Atmosphere
Species thumbnails have a distinctive sci-fi texture:
- Bayer dithering pattern on backgrounds (pixelated gradient texture)
- CRT scan lines and chromatic aberration (RGB color fringing on edges)
- Film grain/noise overlay
- The overall vibe is: ominous, technological, documentary-grade, slightly dystopian

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
      "layout": "The compositional layout used (from the LAYOUTS section above, or your own if none assigned)",
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
        if current_version != self.PROMPT_VERSION or 'Generate TWO distinct' in current or '### The 10 Angles' in current or '{{COUNT}}' not in current or 'Assembly Line' in current or 'Shoggoths' in current or 'Muted, graded, intentional' in current or '## CRITICAL RULES' not in current:
            print("[PROMPT MANAGER] Migrating stale prompt template to current version")
            defaults = self._get_default_prompts()
            self.prompts['claude_prompt'] = defaults['claude_prompt']
            self.prompts['_version'] = self.PROMPT_VERSION
            # Also update image_prompt_template and prompting guide
            self.prompts['image_prompt_template'] = self._get_default_image_prompt_template()
            self.prompts['prompting_guide'] = self._get_default_prompting_guide()
            self.prompting_guide_file.write_text(self.prompts['prompting_guide'])
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

    def build_full_prompt(self, titles: list[str], script: str = "", creative_direction: str = "", count: int = 20, use_layouts: bool = True) -> str:
        """Build the full Claude prompt by filling in the template.

        Returns the prompt string. If use_layouts is True, also stores
        self._last_picked_layouts for downstream tagging.
        """
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

        # Build layout section
        layout_section = ""
        self._last_picked_layouts = []
        if use_layouts:
            from .layouts import build_layout_prompt_section
            layout_section, self._last_picked_layouts = build_layout_prompt_section(count)
            layout_section = layout_section + "\n\n"

        # Fill in placeholders
        prompt = template.replace('{{TITLES}}', titles_formatted)
        prompt = prompt.replace('{{SCRIPT_SECTION}}', script_section)
        prompt = prompt.replace('{{CREATIVE_DIRECTION_SECTION}}', cd_section)
        prompt = prompt.replace('{{COUNT}}', str(count))

        # Insert layout section before the CRITICAL RULES section
        if layout_section and "## CRITICAL RULES" in prompt:
            prompt = prompt.replace("## CRITICAL RULES", layout_section + "## CRITICAL RULES")
        elif layout_section:
            prompt = prompt + "\n\n" + layout_section

        return prompt

    def get_last_picked_layouts(self):
        """Return layouts picked during the last build_full_prompt call."""
        return getattr(self, '_last_picked_layouts', [])
