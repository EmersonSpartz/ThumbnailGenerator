"""
Claude Client - Generate thumbnail concepts using Claude with extended thinking.

Enhanced with:
- Learning from favorites/winners
- Variation generation from existing concepts
"""

import anthropic
import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

# Global log storage for visibility
_last_prompt = ""
_last_response = ""
_last_thinking = ""
_current_thinking = ""  # For real-time streaming
_current_response = ""  # For real-time streaming

def get_last_prompt():
    return _last_prompt

def get_last_response():
    return _last_response

def get_last_thinking():
    return _last_thinking

def get_current_thinking():
    return _current_thinking

def get_current_response():
    return _current_response

def reset_current_stream():
    global _current_thinking, _current_response
    _current_thinking = ""
    _current_response = ""


class ClaudeIdeator:
    """Generate thumbnail concepts using Claude with extended thinking."""

    def __init__(self, settings, prompt_manager=None):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.budget_tokens = settings.thinking_budget_tokens
        self.prompt_manager = prompt_manager
        self.data_dir = settings.data_dir

    def _get_prompting_guide(self) -> str:
        """Get prompting guide from prompt manager or file."""
        if self.prompt_manager:
            return self.prompt_manager.get_prompt('prompting_guide')
        # Fallback to file
        guide_path = self.data_dir / 'prompting_guide.md'
        if guide_path.exists():
            return guide_path.read_text()
        return ""

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
        global _last_prompt, _last_response, _last_thinking

        prompt = self._build_concepts_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count
        )

        # Store the prompt for debugging
        _last_prompt = prompt

        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract and store thinking and response for debugging
        _last_thinking = ""
        _last_response = ""
        for block in response.content:
            if hasattr(block, 'thinking'):
                _last_thinking = block.thinking
            if hasattr(block, 'text'):
                _last_response = block.text

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
        global _last_prompt, _last_response, _last_thinking, _current_thinking, _current_response

        prompt = self._build_concepts_prompt(
            titles, used_ideas, batch_number, script,
            favorites_context, category_hint, creative_direction, count
        )

        # Store and reset
        _last_prompt = prompt
        _current_thinking = ""
        _current_response = ""
        _last_thinking = ""
        _last_response = ""

        # Yield the prompt first so frontend can display it
        yield {"type": "prompt", "content": prompt}

        # Stream the response
        with self.client.messages.stream(
            model=self.model,
            max_tokens=16000,
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
                        _current_thinking += event.delta.thinking
                        yield {"type": "thinking_delta", "content": event.delta.thinking}
                    elif hasattr(event.delta, 'text'):
                        _current_response += event.delta.text
                        yield {"type": "response_delta", "content": event.delta.text}

                elif event.type == "content_block_stop":
                    pass

                elif event.type == "message_stop":
                    _last_thinking = _current_thinking
                    _last_response = _current_response
                    yield {"type": "complete"}

        # Parse and return concepts
        concepts = self._parse_response_text(_current_response)
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

        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
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
        global _last_prompt, _last_response, _last_thinking, _current_thinking, _current_response

        if not concepts:
            yield {"type": "prompts", "prompts": []}
            return

        prompt = self._build_prompts_prompt(concepts)
        _last_prompt = prompt
        _current_thinking = ""
        _current_response = ""

        yield {"type": "prompt", "content": prompt}

        with self.client.messages.stream(
            model=self.model,
            max_tokens=16000,
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
                        _current_thinking += event.delta.thinking
                        yield {"type": "thinking_delta", "content": event.delta.thinking}
                    elif hasattr(event.delta, 'text'):
                        _current_response += event.delta.text
                        yield {"type": "response_delta", "content": event.delta.text}
                elif event.type == "message_stop":
                    _last_thinking = _current_thinking
                    _last_response = _current_response
                    yield {"type": "complete"}

        # Parse and merge prompts with concepts
        class FakeResponse:
            def __init__(self, text):
                self.content = [type('Block', (), {'text': text})()]
        result = self._parse_prompts(FakeResponse(_current_response), concepts)
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

        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
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

    def _build_prompts_prompt(self, concepts: list[dict]) -> str:
        """Build prompt for STEP 2: NanoBanana Pro prompt writing."""
        concepts_formatted = "\n\n".join([
            f"**{i+1}. {c.get('concept_name', 'Untitled')}** ({c.get('category', 'General')})\n"
            f"Title: {c.get('title_ref', 'Unknown')}\n"
            f"Description: {c.get('description', '')}"
            for i, c in enumerate(concepts)
        ])

        # Get editable prompting guide
        prompting_guide = self._get_prompting_guide()

        # Get image prompt template if available
        image_template = ""
        if self.prompt_manager:
            image_template = self.prompt_manager.get_prompt('image_prompt_template')

        template_instruction = image_template if image_template else "Write NanoBanana Pro prompts for each of these thumbnail concepts. Follow the prompting guide below."

        return f"""{template_instruction}

CRITICAL: DO NOT include any text, words, letters, or numbers in the image. The thumbnail should be purely visual.

## CONCEPTS:

{concepts_formatted}

---

## NANOBANANA PRO PROMPTING GUIDE

{prompting_guide}

---

Return as JSON:
```json
{{
  "prompts": [
    {{
      "concept_name": "The concept name from above",
      "title_ref": "The video title",
      "prompt": "The complete NanoBanana Pro prompt (NO TEXT IN IMAGE)"
    }}
  ]
}}
```"""

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

        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(text)

            prompts = data.get('prompts', [])

            # Merge prompts back with concepts
            result = []
            for prompt_data in prompts:
                concept_name = prompt_data.get('concept_name', '')
                # Find matching concept
                matching_concept = next(
                    (c for c in concepts if c.get('concept_name') == concept_name),
                    {}
                )
                merged = {**matching_concept, **prompt_data}
                result.append(merged)

            return result
        except json.JSONDecodeError:
            print(f"Failed to parse prompts JSON: {text[:500]}")
            return []
