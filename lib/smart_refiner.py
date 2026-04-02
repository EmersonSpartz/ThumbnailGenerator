"""
Smart Refiner — Single-iteration thumbnail refinement using learned patterns.

Completely separate from agentic_refiner.py. Based on empirical testing:
20-round experiment showed ~90% accuracy with comparative evaluation,
and identified 6 consistent improvement patterns.

Two modes:
1. enhance_prompt() — Apply learned patterns to any prompt before generation
2. refine_thumbnail() — Given a generated thumbnail, diagnose + generate improved version
"""

import os
import base64
import json
from pathlib import Path
from typing import Optional
import anthropic


# Fallback patterns (used if learned_patterns.json doesn't exist)
_FALLBACK_PATTERNS = """
Based on empirical A/B testing of 20 thumbnail pairs, these changes consistently improved
click-worthiness at YouTube thumbnail size (320x180px):

1. DARK/BLACK BACKGROUND (used in 17/19 improvements): Replace natural/busy backgrounds with
   "pure black background" or "pitch-black background". This creates instant subject separation.

2. EXTREME CLOSE-UP (14/19): Use "extreme close-up" or "filling the frame". The subject should
   dominate 50-70% of the frame. Small subjects get lost at thumbnail size.

3. HIGH-CONTRAST ACCENT COLORS (12/19): Specify vivid, saturated colors for the subject against
   the dark background. Name exact colors: "vivid orange-amber", "bright crimson", "electric blue".

4. SINGLE FOCAL POINT (11/19): Remove secondary elements, clutter, and environmental details.
   One bold subject reads instantly; multiple elements become mud at 320px.

5. CONCEPT STORYTELLING (6/19): Make the image SHOW the concept, not just the animal.
   E.g., for "regeneration" show a regrowing limb; for "transformation" show a visual split.

6. TEXT OVERLAY SPACE (4/19): Leave dark empty space (often right third) for bold text overlay.
"""


def load_patterns(base_dir: Path = None) -> str:
    """Load learned patterns from JSON file, fallback to hardcoded."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    patterns_file = base_dir / "data" / "learned_patterns.json"
    try:
        with open(patterns_file) as f:
            data = json.load(f)
        return data.get("prompt_text", _FALLBACK_PATTERNS)
    except (FileNotFoundError, json.JSONDecodeError):
        return _FALLBACK_PATTERNS


# Module-level convenience (loaded once, refreshed by calling load_patterns())
LEARNED_PATTERNS = load_patterns()

REFERENCE_IMAGES = [
    "training_data/9D79XIHYMP4.png",   # "Self Aware" - robots
    "training_data/FaBpwOGKBok.png",    # "Don't Trust Them" - woman with mask
    "training_data/D8RtMHuFsUw.png",   # "7 Minute War" - graph
]


def _encode_image(path: Path) -> tuple:
    """Encode image to base64, return (base64_str, media_type)."""
    ext = path.suffix.lower()
    media_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
    media_type = media_types.get(ext, 'image/jpeg')
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8'), media_type


def _make_image_block(path: Path) -> dict:
    """Create a Claude API image content block."""
    data, media_type = _encode_image(path)
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def enhance_prompt(prompt: str, concept_name: str = "", api_key: str = "") -> str:
    """
    Apply learned patterns to a prompt BEFORE generation.
    Fast — single short API call. No image generation needed.

    This is the "make every first generation better" approach.
    """
    if not api_key:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return prompt  # Silently return original if no key

    client = anthropic.Anthropic(api_key=api_key)

    enhancement_prompt = f"""You're optimizing an image generation prompt for a YouTube thumbnail.

**Original prompt**: {prompt}
**Concept**: {concept_name or 'not specified'}

{LEARNED_PATTERNS}

Apply these patterns to improve the prompt. Rules:
- Keep the prompt SIMILAR LENGTH (±10 words) to the original
- REPLACE weak elements, don't add more words
- Ensure a dark/black background is specified
- Ensure the subject fills the frame (extreme close-up if appropriate)
- Specify at least one vivid accent color by name
- Remove any "natural environment" or "foliage" elements that would create clutter
- Keep the "no text, no words, no letters, no logos" suffix

Return ONLY the improved prompt text. No explanation."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",  # Fast + cheap for this task
            max_tokens=500,
            timeout=10.0,  # Hard 10s timeout — don't block generation
            messages=[{"role": "user", "content": enhancement_prompt}]
        )
        enhanced = response.content[0].text.strip().strip('"\'')
        return enhanced
    except Exception as e:
        print(f"[SMART REFINER] Enhancement failed, using original: {e}")
        return prompt


def refine_thumbnail(image_path: Path, original_prompt: str, concept_name: str,
                     api_key: str = "", base_dir: Path = None) -> dict:
    """
    Diagnose a thumbnail's biggest weakness and generate a refined prompt.
    Uses reference images for aesthetic calibration.

    Returns:
        {
            "weakness": str,
            "refined_prompt": str,
            "feeling": str  # bad/mediocre/decent/good/great
        }
    """
    if not api_key:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    client = anthropic.Anthropic(api_key=api_key)

    content = []

    # Add reference images
    content.append({"type": "text", "text": "**REFERENCE: Real Species channel thumbnails — match this quality and sensibility:**"})
    for ref_path in REFERENCE_IMAGES:
        p = base_dir / ref_path
        if p.exists():
            content.append(_make_image_block(p))

    # Add the thumbnail to evaluate
    content.append({"type": "text", "text": f"\n\n**Evaluate this thumbnail for: \"{concept_name}\"**"})
    content.append(_make_image_block(image_path))
    content.append({"type": "text", "text": f"Prompt used: {original_prompt}"})

    max_words = int(len(original_prompt.split()) * 1.2)

    content.append({"type": "text", "text": f"""
{LEARNED_PATTERNS}

Looking at this as a YouTube thumbnail at 320x180px:

1. What's the SINGLE biggest weakness that would hurt click-through rate?
2. Which of the 6 learned patterns would fix it?
3. What specific prompt change implements that fix?

Respond with JSON:
{{
    "feeling": "bad" or "mediocre" or "decent" or "good" or "great",
    "weakness": "The ONE thing to fix",
    "pattern_used": "Which of the 6 patterns addresses this",
    "refined_prompt": "Improved prompt fixing ONLY that weakness. Max {max_words} words — replace weak parts, don't pile on."
}}"""})

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            system="You're a creative collaborator for the Species YouTube channel. Be specific and honest. Focus on thumbnail-size impact.",
            messages=[{"role": "user", "content": content}]
        )

        text = response.content[0].text
        if "```json" in text:
            text = text[text.find("```json") + 7:text.find("```", text.find("```json") + 7)].strip()
        elif "```" in text:
            text = text[text.find("```") + 3:text.find("```", text.find("```") + 3)].strip()

        return json.loads(text)

    except Exception as e:
        return {
            "feeling": "unknown",
            "weakness": f"Evaluation failed: {e}",
            "pattern_used": "none",
            "refined_prompt": original_prompt
        }


def compare_thumbnails(img_a: Path, img_b: Path, concept_name: str,
                       prompt_a: str, prompt_b: str,
                       api_key: str = "", base_dir: Path = None) -> dict:
    """
    Compare two thumbnails and determine which is better.
    Uses reference images for calibration.

    Returns:
        {"winner": "A"|"B"|"tie", "reasoning": str}
    """
    if not api_key:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    client = anthropic.Anthropic(api_key=api_key)

    content = []

    # References
    content.append({"type": "text", "text": "**REFERENCE thumbnails from the Species channel:**"})
    for ref_path in REFERENCE_IMAGES:
        p = base_dir / ref_path
        if p.exists():
            content.append(_make_image_block(p))

    # The two candidates — DON'T label which is "original" vs "refined" to avoid bias
    content.append({"type": "text", "text": f"\n\n**Compare these two thumbnails for: \"{concept_name}\"**"})
    content.append({"type": "text", "text": "\n**IMAGE A:**"})
    content.append(_make_image_block(img_a))
    content.append({"type": "text", "text": "\n**IMAGE B:**"})
    content.append(_make_image_block(img_b))

    content.append({"type": "text", "text": """
Which thumbnail would get more clicks on YouTube at 320x180px?
Think about: visual impact, composition, focal point, Species channel aesthetic.

Respond with JSON:
{"winner": "A" or "B" or "tie", "reasoning": "Why — be specific and concise"}"""})

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=500,
            system="You're evaluating YouTube thumbnails. Be honest — say 'tie' if they're genuinely similar. Focus on thumbnail-size impact.",
            messages=[{"role": "user", "content": content}]
        )

        text = response.content[0].text
        if "```json" in text:
            text = text[text.find("```json") + 7:text.find("```", text.find("```json") + 7)].strip()
        elif "```" in text:
            text = text[text.find("```") + 3:text.find("```", text.find("```") + 3)].strip()

        return json.loads(text)

    except Exception as e:
        return {"winner": "unknown", "reasoning": f"Comparison failed: {e}"}
