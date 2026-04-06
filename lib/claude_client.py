"""
Claude Client - Generate thumbnail concepts using Claude with extended thinking.

Enhanced with:
- Learning from favorites/winners
- Variation generation from existing concepts
"""

import anthropic
import json
import re
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

# Thread-local storage for per-request visibility (safe for concurrent users)
import threading
_thread_local = threading.local()

def _get_tls():
    """Get thread-local storage, initializing defaults if needed."""
    if not hasattr(_thread_local, 'last_prompt'):
        _thread_local.last_prompt = ""
        _thread_local.last_response = ""
        _thread_local.last_thinking = ""
        _thread_local.current_thinking = ""
        _thread_local.current_response = ""
    return _thread_local

def get_last_prompt():
    return _get_tls().last_prompt

def get_last_response():
    return _get_tls().last_response

def get_last_thinking():
    return _get_tls().last_thinking

def get_current_thinking():
    return _get_tls().current_thinking

def get_current_response():
    return _get_tls().current_response

def reset_current_stream():
    tls = _get_tls()
    tls.current_thinking = ""
    tls.current_response = ""


SPECIES_SYSTEM_MESSAGE = (
    "You're a creative collaborator helping the Species YouTube channel — "
    "a premium AI safety channel — design compelling thumbnails. "
    "You're working alongside Emerson (the creator) and an image generation model. "
    "Your role is to bring creative vision and critical eye to the process. "
    "Have fun with it — the best thumbnails come from genuine creative enthusiasm."
)


class ClaudeIdeator:
    """Generate thumbnail concepts using Claude with extended thinking."""

    def __init__(self, settings, prompt_manager=None):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)
        self.model = settings.claude_model
        self.budget_tokens = settings.thinking_budget_tokens
        self.prompt_manager = prompt_manager
        self.data_dir = settings.data_dir

    def _stream_with_retry(self, max_retries=3, **kwargs):
        """Stream a Claude message with retry on connection/rate limit errors."""
        if 'system' not in kwargs:
            kwargs['system'] = SPECIES_SYSTEM_MESSAGE
        for attempt in range(max_retries):
            try:
                with self.client.messages.stream(**kwargs) as stream:
                    return stream.get_final_message()
            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APITimeoutError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                print(f"[Claude] Retry {attempt + 1}/{max_retries} after {type(e).__name__}: waiting {wait}s")
                time.sleep(wait)


    def generate_concepts_and_prompts_streaming(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20,
        thumbnail_text: str = ""
    ):
        """
        COMBINED: Generate concepts AND image prompts in a single Claude call.
        Saves ~35 seconds by eliminating the second API call.
        Yields streaming events, then final {"type": "prompts_ready", "prompts": [...]}.
        """
        tls = _get_tls()

        prompt = self._build_combined_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count,
            thumbnail_text=thumbnail_text
        )

        tls.last_prompt = prompt
        tls.current_thinking = ""
        tls.current_response = ""
        tls.last_thinking = ""
        tls.last_response = ""

        yield {"type": "prompt", "content": prompt}

        # More tokens needed since we're generating both concepts + prompts
        tokens_needed = max(16000, count * 900 + self.budget_tokens + 8000)
        tokens_needed = min(tokens_needed, 32000)  # Opus 4 max output is 32k

        with self.client.messages.stream(
            model=self.model,
            system=SPECIES_SYSTEM_MESSAGE,
            max_tokens=tokens_needed,
            thinking={"type": "enabled", "budget_tokens": self.budget_tokens},
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, 'type'):
                        if event.content_block.type == "thinking":
                            yield {"type": "thinking_start"}
                        elif event.content_block.type == "text":
                            yield {"type": "response_start"}
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, 'thinking'):
                        tls.current_thinking += event.delta.thinking
                        yield {"type": "thinking_delta", "content": event.delta.thinking}
                    elif hasattr(event.delta, 'text'):
                        tls.current_response += event.delta.text
                        yield {"type": "response_delta", "content": event.delta.text}
                elif event.type == "message_stop":
                    tls.last_thinking = tls.current_thinking
                    tls.last_response = tls.current_response
                    yield {"type": "complete"}

        # Parse combined response
        result = self._parse_combined_response(tls.current_response)
        yield {"type": "prompts_ready", "prompts": result}

    def generate_concepts_and_prompts(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20,
        thumbnail_text: str = ""
    ) -> list[dict]:
        """
        COMBINED (non-streaming): Generate concepts AND image prompts in a single Claude call.
        Returns list of dicts with concept_name, category, description, title_ref, and prompt.
        """
        tls = _get_tls()

        prompt = self._build_combined_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count,
            thumbnail_text=thumbnail_text
        )

        tls.last_prompt = prompt

        tokens_needed = max(16000, count * 900 + self.budget_tokens + 8000)
        tokens_needed = min(tokens_needed, 32000)  # Opus 4 max output is 32k

        response = self._stream_with_retry(
            model=self.model,
            max_tokens=tokens_needed,
            thinking={"type": "enabled", "budget_tokens": self.budget_tokens},
            messages=[{"role": "user", "content": prompt}]
        )

        tls.last_thinking = ""
        tls.last_response = ""
        for block in response.content:
            if hasattr(block, 'thinking'):
                tls.last_thinking = block.thinking
            if hasattr(block, 'text'):
                tls.last_response = block.text

        return self._parse_combined_response(tls.last_response)

    def generate_concepts(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20
    ) -> list[dict]:
        """
        STEP 1: Generate thumbnail concepts/ideas.
        Returns creative concepts without detailed prompts yet.

        Args:
            titles: List of possible video titles
            used_ideas: Previously generated ideas to avoid
            batch_number: Current batch number
            script: Optional video script for context
            favorites_context: Summary of successful thumbnails to learn from
            category_hint: Hint to focus on specific categories
            creative_direction: User's guidance on visual style (e.g., "fungal body horror")
            count: Number of concepts to generate
        """
        tls = _get_tls()

        prompt = self._build_concepts_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count
        )

        # Store the prompt for debugging
        tls.last_prompt = prompt

        response = self._stream_with_retry(
            model=self.model,
            max_tokens=32000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract and store thinking and response for debugging
        tls.last_thinking = ""
        tls.last_response = ""
        for block in response.content:
            if hasattr(block, 'thinking'):
                tls.last_thinking = block.thinking
            if hasattr(block, 'text'):
                tls.last_response = block.text

        return self._parse_concepts(response)

    def generate_concepts_streaming(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20
    ):
        """
        STEP 1: Generate thumbnail concepts with streaming for real-time visibility.
        Yields events as Claude thinks and writes.
        """
        tls = _get_tls()

        prompt = self._build_concepts_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count
        )

        # Store and reset
        tls.last_prompt = prompt
        tls.current_thinking = ""
        tls.current_response = ""
        tls.last_thinking = ""
        tls.last_response = ""

        # Yield the prompt first so frontend can display it
        yield {"type": "prompt", "content": prompt}

        # Scale max_tokens based on concept count (~200 tokens per concept in JSON)
        # thinking budget is separate, so we need enough for the full JSON response
        response_tokens_needed = max(32000, count * 300 + self.budget_tokens + 5000)
        response_tokens_needed = min(response_tokens_needed, 32000)  # API limit

        # Stream the response
        with self.client.messages.stream(
            model=self.model,
            system=SPECIES_SYSTEM_MESSAGE,
            max_tokens=response_tokens_needed,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, 'type'):
                        if event.content_block.type == "thinking":
                            yield {"type": "thinking_start"}
                        elif event.content_block.type == "text":
                            yield {"type": "response_start"}

                elif event.type == "content_block_delta":
                    if hasattr(event.delta, 'thinking'):
                        tls.current_thinking += event.delta.thinking
                        yield {"type": "thinking_delta", "content": event.delta.thinking}
                    elif hasattr(event.delta, 'text'):
                        tls.current_response += event.delta.text
                        yield {"type": "response_delta", "content": event.delta.text}

                elif event.type == "content_block_stop":
                    pass

                elif event.type == "message_stop":
                    tls.last_thinking = tls.current_thinking
                    tls.last_response = tls.current_response
                    yield {"type": "complete"}

        # Parse and return concepts
        concepts = self._parse_response_text(tls.current_response)
        yield {"type": "concepts", "concepts": concepts}

    def _parse_response_text(self, text: str) -> list[dict]:
        """Parse concepts from response text."""
        # Find all JSON code blocks and try each one until one parses
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)

        for json_str in json_blocks:
            try:
                data = json.loads(json_str)
                concepts = data.get('concepts', [])
                if concepts:  # Found valid concepts
                    return concepts
            except json.JSONDecodeError:
                continue  # Try next block

        # Fallback: try parsing entire text as JSON
        try:
            data = json.loads(text)
            return data.get('concepts', [])
        except json.JSONDecodeError:
            pass

        # Last resort: look for a JSON object anywhere in the text
        try:
            json_match = re.search(r'\{\s*"concepts"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return data.get('concepts', [])
        except json.JSONDecodeError:
            pass

        # Recover individual concept objects from truncated JSON
        concept_objects = re.findall(
            r'\{\s*"title_ref"\s*:\s*"[^"]*"\s*,\s*"concept_name"\s*:\s*"[^"]+"\s*,\s*(?:"layout"\s*:\s*"[^"]*"\s*,\s*)?(?:"category"\s*:\s*"[^"]*"\s*,\s*)?"description"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}',
            text, re.DOTALL
        )
        if concept_objects:
            recovered = []
            for obj_str in concept_objects:
                try:
                    recovered.append(json.loads(obj_str))
                except json.JSONDecodeError:
                    continue
            if recovered:
                print(f"[PARSE] Recovered {len(recovered)} concepts from truncated JSON")
                return recovered

        print(f"Failed to parse concepts JSON: {text[:500]}")
        return []

    def generate_prompts_for_concepts(self, concepts: list[dict]) -> list[dict]:
        """
        STEP 2: Generate NanoBanana Pro prompts for the concepts.
        Uses the prompting guide to write detailed image generation prompts.
        """
        if not concepts:
            return []

        prompt = self._build_prompts_prompt(concepts)

        response = self._stream_with_retry(
            model=self.model,
            max_tokens=32000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_prompts(response, concepts)

    def generate_prompts_for_concepts_streaming(self, concepts: list[dict]):
        """
        STEP 2: Generate prompts with streaming for real-time visibility.
        Yields events as Claude thinks and writes.
        """
        tls = _get_tls()

        if not concepts:
            yield {"type": "prompts", "prompts": []}
            return

        prompt = self._build_prompts_prompt(concepts)
        tls.last_prompt = prompt
        tls.current_thinking = ""
        tls.current_response = ""

        yield {"type": "prompt", "content": prompt}

        # Scale tokens for large concept counts (~600 tokens per detailed image prompt)
        prompt_tokens_needed = max(32000, len(concepts) * 600 + self.budget_tokens + 5000)
        prompt_tokens_needed = min(prompt_tokens_needed, 32000)

        with self.client.messages.stream(
            model=self.model,
            system=SPECIES_SYSTEM_MESSAGE,
            max_tokens=prompt_tokens_needed,
            thinking={"type": "enabled", "budget_tokens": self.budget_tokens},
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, 'type'):
                        if event.content_block.type == "thinking":
                            yield {"type": "thinking_start"}
                        elif event.content_block.type == "text":
                            yield {"type": "response_start"}
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, 'thinking'):
                        tls.current_thinking += event.delta.thinking
                        yield {"type": "thinking_delta", "content": event.delta.thinking}
                    elif hasattr(event.delta, 'text'):
                        tls.current_response += event.delta.text
                        yield {"type": "response_delta", "content": event.delta.text}
                elif event.type == "message_stop":
                    tls.last_thinking = tls.current_thinking
                    tls.last_response = tls.current_response
                    yield {"type": "complete"}

        # Parse and merge prompts with concepts
        class FakeResponse:
            def __init__(self, text):
                self.content = [type('Block', (), {'text': text})()]
        result = self._parse_prompts(FakeResponse(tls.current_response), concepts)
        yield {"type": "prompts", "prompts": result}

    def generate_variations(
        self,
        base_concept: dict,
        num_variations: int = 5,
        variation_style: str = "similar"
    ) -> list[dict]:
        """
        Generate variations of a successful/favorite thumbnail concept.

        Args:
            base_concept: The concept to base variations on
            num_variations: How many variations to generate
            variation_style: "similar" (close to original), "explore" (more different),
                           or "remix" (combine with other elements)
        """
        prompt = self._build_variations_prompt(base_concept, num_variations, variation_style)

        response = self._stream_with_retry(
            model=self.model,
            max_tokens=32000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        )

        return self._parse_concepts(response)

    def _build_concepts_prompt(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20
    ) -> str:
        """Build prompt for STEP 1: Concept ideation - uses editable prompt from file."""
        # Use prompt manager if available, otherwise lazy-load it
        if self.prompt_manager is None:
            from .prompt_manager import PromptManager
            self.prompt_manager = PromptManager(self.data_dir)

        # Build prompt using the editable template
        return self.prompt_manager.build_full_prompt(
            titles=titles,
            script=script or "",
            creative_direction=creative_direction or "",
            count=count
        )

    def _get_learned_patterns(self) -> str:
        """Load learned patterns from A/B testing (if available)."""
        try:
            from lib.smart_refiner import load_patterns
            patterns = load_patterns(self.data_dir.parent if self.data_dir else None)
            if patterns and len(patterns) > 50:
                return patterns
        except Exception:
            pass
        return ""

    def _get_avoid_rules(self) -> str:
        """Load failure-avoidance rules from bottom-25% analysis."""
        try:
            avoid_file = (self.data_dir if self.data_dir else Path(__file__).parent.parent / 'data') / 'avoid_patterns.json'
            with open(avoid_file) as f:
                data = json.load(f)
            rules = data.get('avoid_rules', [])
            if not rules:
                return ""
            lines = []
            for r in rules:
                lines.append(f"- {r['rule']}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_prompts_prompt(self, concepts: list[dict]) -> str:
        """Build prompt for STEP 2: image prompt writing from pre-existing concepts."""
        concepts_formatted = "\n\n".join([
            f"**{i+1}. {c.get('concept_name', 'Untitled')}** ({c.get('category', 'General')})\n"
            f"Title: {c.get('title_ref', 'Unknown')}\n"
            f"Description: {c.get('description', '')}"
            for i, c in enumerate(concepts)
        ])

        learned_patterns = self._get_learned_patterns()
        avoid_rules = self._get_avoid_rules()

        return f"""Write a detailed image generation prompt for each thumbnail concept below.

## CONCEPTS

{concepts_formatted}

---

## IMAGE PROMPT RULES

1. NO text/words/letters/numbers in the image
2. Dark textured background (grain, dither — not pure void)
3. ONE bold subject filling 60%+ of the frame — readable at 320px
4. Red (#E20020) as primary accent. Secondary: cyan (#22E2FF), magenta (#F732EF)
5. Photorealistic cinematic rendering — NOT cartoon, NOT comic book, NOT cel-shaded
6. End every prompt with: no text, no words, no letters, 16:9, dark textured background, photorealistic, NOT cartoon
{f'''
## LEARNED PATTERNS (from A/B testing — apply these)

{learned_patterns}''' if learned_patterns else ''}
{f'''
## AVOID THESE (from failure analysis)

{avoid_rules}''' if avoid_rules else ''}

---

## OUTPUT FORMAT

Return as JSON:
```json
{{
  "prompts": [
    {{
      "concept_name": "The concept name from above",
      "title_ref": "The video title",
      "prompt": "Complete image prompt (end with: no text, no words, no letters, 16:9, photorealistic, NOT cartoon)"
    }}
  ]
}}
```"""

    def _build_combined_prompt(
        self,
        titles: list[str],
        used_ideas: list[str],
        batch_number: int,
        script: str = None,
        favorites_context: str = "",
        category_hint: str = "",
        creative_direction: str = "",
        count: int = 20,
        thumbnail_text: str = ""
    ) -> str:
        """Build a single, consolidated prompt — no redundancy."""
        if self.prompt_manager is None:
            from .prompt_manager import PromptManager
            self.prompt_manager = PromptManager(self.data_dir)

        # Get the user-editable concept generation template
        base_prompt = self.prompt_manager.build_full_prompt(
            titles=titles,
            script=script or "",
            creative_direction=creative_direction or "",
            count=count
        )

        # Get learned patterns and avoid rules (these are the self-improving parts)
        learned_patterns = self._get_learned_patterns()
        avoid_rules = self._get_avoid_rules()

        # Thumbnail text context
        thumb_text_line = f'\n**THUMBNAIL TEXT**: "{thumbnail_text}" will be overlaid on the image. Design compositions that complement this text — leave space for it and let the imagery enhance its meaning.\n' if thumbnail_text else ''

        return f"""{base_prompt}
{thumb_text_line}
---

## IMAGE PROMPT RULES

For each concept, also write a detailed image generation prompt. Rules:

1. NO text/words/letters/numbers in the image
2. Dark textured background (grain, dither — not pure void)
3. ONE bold subject filling 60%+ of the frame — readable at 320px
4. Red (#E20020) as primary accent. Secondary: cyan (#22E2FF), magenta (#F732EF)
5. Photorealistic cinematic rendering — NOT cartoon, NOT comic book, NOT cel-shaded
6. End every prompt with: no text, no words, no letters, 16:9, dark textured background, photorealistic, NOT cartoon
{f'''
## LEARNED PATTERNS (from A/B testing — apply these)

{learned_patterns}''' if learned_patterns else ''}
{f'''
## AVOID THESE (from failure analysis)

{avoid_rules}''' if avoid_rules else ''}

---

## OUTPUT FORMAT

Return {count} concepts as JSON:
```json
{{
  "concepts": [
    {{
      "title_ref": "video title",
      "concept_name": "2-4 word name",
      "category": "Cinematic Scale / Intimate Portrait / Bold Metaphor / etc.",
      "description": "2-3 sentence visual description",
      "prompt": "Complete image prompt (end with: no text, no words, no letters, 16:9, photorealistic, NOT cartoon)"
    }}
  ]
}}
```"""

    def _parse_combined_response(self, text: str) -> list[dict]:
        """Parse the combined concepts+prompts response."""
        # Try JSON code blocks first
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        for json_str in json_blocks:
            try:
                data = json.loads(json_str)
                concepts = data.get('concepts', [])
                if concepts:
                    # Ensure every concept has a prompt — synthesize from description if missing
                    for c in concepts:
                        if not c.get('prompt') and c.get('description'):
                            c['prompt'] = c['description'] + ', no text, no words, no letters, 16:9 aspect ratio, dark textured background, bold minimal composition, ominous red accent lighting, photorealistic rendering, NOT cartoon, NOT comic book, NOT cel-shaded'
                            print(f"[PARSE] Synthesized prompt from description for '{c.get('concept_name', '?')}'")
                    if any(c.get('prompt') for c in concepts):
                        return concepts
            except json.JSONDecodeError:
                continue

        # Fallback: try entire text as JSON
        try:
            data = json.loads(text)
            concepts = data.get('concepts', [])
            for c in concepts:
                if not c.get('prompt') and c.get('description'):
                    c['prompt'] = c['description'] + ', no text, no words, no letters, 16:9 aspect ratio, dark textured background, bold minimal composition, ominous red accent lighting, photorealistic rendering, NOT cartoon, NOT comic book, NOT cel-shaded'
            return concepts
        except json.JSONDecodeError:
            pass

        # Last resort: find JSON object in text
        try:
            json_match = re.search(r'\{\s*"concepts"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return data.get('concepts', [])
        except json.JSONDecodeError:
            pass

        # Recover individual objects from truncated JSON
        concept_objects = re.findall(
            r'\{\s*"title_ref"\s*:\s*"[^"]*"\s*,\s*"concept_name"\s*:\s*"[^"]+"\s*,\s*(?:"layout"\s*:\s*"[^"]*"\s*,\s*)?(?:"category"\s*:\s*"[^"]*"\s*,\s*)?"description"\s*:\s*"(?:[^"\\]|\\.)*"\s*,\s*"prompt"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}',
            text, re.DOTALL
        )
        if concept_objects:
            recovered = []
            for obj_str in concept_objects:
                try:
                    recovered.append(json.loads(obj_str))
                except json.JSONDecodeError:
                    continue
            if recovered:
                print(f"[PARSE] Recovered {len(recovered)} combined concepts from truncated JSON")
                return recovered

        print(f"Failed to parse combined response: {text[:500]}")
        return []

    def _build_variations_prompt(
        self,
        base_concept: dict,
        num_variations: int,
        variation_style: str
    ) -> str:
        """Build prompt for generating variations of a successful concept."""

        style_instructions = {
            "similar": "Create variations that are close to the original but with subtle differences in composition, color, or angle.",
            "explore": "Create variations that explore different interpretations of the same core idea. Be more creative and experimental.",
            "remix": "Create variations that combine the successful elements with new unexpected elements."
        }

        return f"""Generate {num_variations} variations of this successful thumbnail concept.

## ORIGINAL CONCEPT
- Name: {base_concept.get('concept_name', 'Unknown')}
- Category: {base_concept.get('category', 'Unknown')}
- Description: {base_concept.get('description', '')}
- Original Prompt: {base_concept.get('prompt', 'N/A')}
- Why it worked: {base_concept.get('notes', 'Not specified')}

## VARIATION STYLE
{style_instructions.get(variation_style, style_instructions['similar'])}

---

Create {num_variations} variation concepts that build on what made the original successful.

For each variation, give:
1. A short memorable name (reference the original)
2. A brief description of how this varies from the original
3. Keep the same category: {base_concept.get('category', 'General')}

Return as JSON:
```json
{{
  "concepts": [
    {{
      "title_ref": "{base_concept.get('title_ref', 'Unknown')}",
      "concept_name": "Variation name",
      "category": "{base_concept.get('category', 'General')}",
      "description": "How this variation differs",
      "based_on": "{base_concept.get('concept_name', 'Unknown')}"
    }}
  ]
}}
```"""

    def _parse_concepts(self, response) -> list[dict]:
        """Parse concepts from Claude's response."""
        # Extract text from response
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text = block.text
                break

        # Use the robust parser
        return self._parse_response_text(text)

    def _parse_prompts(self, response, concepts: list[dict]) -> list[dict]:
        """Parse prompts from Claude's response and merge with concepts."""
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text = block.text
                break

        prompts = []
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(text)
            prompts = data.get('prompts', [])
        except json.JSONDecodeError:
            # JSON truncated — recover individual prompt objects from partial JSON
            prompt_objects = re.findall(
                r'\{\s*"concept_name"\s*:\s*"[^"]+"\s*,\s*"title_ref"\s*:\s*"[^"]*"\s*,\s*"prompt"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}',
                text, re.DOTALL
            )
            for obj_str in prompt_objects:
                try:
                    prompts.append(json.loads(obj_str))
                except json.JSONDecodeError:
                    continue
            if prompts:
                print(f"[PARSE] Recovered {len(prompts)} prompts from truncated JSON")
            else:
                print(f"Failed to parse prompts JSON: {text[:500]}")

        # Merge prompts back with concepts
        result = []
        for prompt_data in prompts:
            concept_name = prompt_data.get('concept_name', '')
            matching_concept = next(
                (c for c in concepts if c.get('concept_name') == concept_name),
                {}
            )
            merged = {**matching_concept, **prompt_data}
            result.append(merged)

        return result
