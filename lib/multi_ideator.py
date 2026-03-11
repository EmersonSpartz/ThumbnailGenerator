"""
Multi-LLM Ideation - Generate concepts with Claude, ChatGPT, and Gemini in parallel.

This maximizes diversity by getting different creative perspectives from each LLM.
"""

import json
import re
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from abc import ABC, abstractmethod

# Claude
import anthropic

# OpenAI (ChatGPT)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Google Gemini (text)
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class IdeatorBase(ABC):
    """Base class for LLM ideators."""

    @abstractmethod
    def generate_concepts(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> list[dict]:
        """Generate thumbnail concepts."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this ideator."""
        pass

    def _build_concepts_prompt(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> str:
        """Build the prompt for concept generation (shared across LLMs)."""
        titles_formatted = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])

        if script and script.strip():
            base_prompt = f"""Here's a video script. Generate {num_concepts} unique YouTube thumbnail concepts.

## VIDEO SCRIPT
{script}

## POSSIBLE TITLES
{titles_formatted}
"""
        else:
            base_prompt = f"""Generate {num_concepts} unique YouTube thumbnail concepts for these video titles:

{titles_formatted}
"""

        if favorites_context:
            base_prompt += f"""
## SUCCESSFUL EXAMPLES TO LEARN FROM
{favorites_context}

Use these as inspiration for what works well.
"""

        if used_ideas:
            used_formatted = ", ".join(used_ideas[:30])
            base_prompt += f"""
## IDEAS TO AVOID (already used)
{used_formatted}

Generate DIFFERENT concepts.
"""

        base_prompt += f"""
Create {num_concepts} visually striking, click-worthy thumbnail concepts.

For each concept provide:
1. A short memorable name
2. A vivid visual description (2-3 sentences)
3. A category (Dramatic, Mysterious, Tech, Human Interest, Comparison, Shocking, Educational)

Return ONLY valid JSON:
```json
{{
  "concepts": [
    {{
      "title_ref": "Which video title this relates to",
      "concept_name": "Short memorable name",
      "category": "Category",
      "description": "Vivid visual description"
    }}
  ]
}}
```"""
        return base_prompt

    def _parse_concepts(self, text: str) -> list[dict]:
        """Parse concepts from LLM response."""
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try to find JSON object directly
                json_match = re.search(r'\{[\s\S]*"concepts"[\s\S]*\}', text)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    data = json.loads(text)
            return data.get('concepts', [])
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from {self.get_name()}: {e}")
            return []


class ClaudeIdeatorV2(IdeatorBase):
    """Generate concepts using Claude with extended thinking."""

    def __init__(self, settings):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.budget_tokens = settings.thinking_budget_tokens

    def get_name(self) -> str:
        return "Claude"

    def generate_concepts(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> list[dict]:
        prompt = self._build_concepts_prompt(titles, used_ideas, script, favorites_context, num_concepts)

        # Ensure max_tokens > budget_tokens for extended thinking
        max_tokens = max(16000, self.budget_tokens + 4000)
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            thinking={
                "type": "enabled",
                "budget_tokens": self.budget_tokens
            },
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            response = stream.get_final_message()

        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text = block.text
                break

        concepts = self._parse_concepts(text)
        # Tag concepts with source
        for c in concepts:
            c['source_llm'] = 'claude'
        return concepts


class ChatGPTIdeator(IdeatorBase):
    """Generate concepts using ChatGPT (GPT-4)."""

    def __init__(self, settings):
        self.api_key = os.getenv('OPENAI_API_KEY', '')
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o')
        if self.api_key and OPENAI_AVAILABLE:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            self.client = None

    def get_name(self) -> str:
        return "ChatGPT"

    def is_available(self) -> bool:
        return self.client is not None and OPENAI_AVAILABLE

    def generate_concepts(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> list[dict]:
        if not self.is_available():
            return []

        prompt = self._build_concepts_prompt(titles, used_ideas, script, favorites_context, num_concepts)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a creative YouTube thumbnail designer. Generate bold, visually striking concepts that drive clicks."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.9  # Higher creativity
            )

            text = response.choices[0].message.content
            concepts = self._parse_concepts(text)
            # Tag concepts with source
            for c in concepts:
                c['source_llm'] = 'chatgpt'
            return concepts
        except Exception as e:
            print(f"ChatGPT error: {e}")
            return []


class GeminiIdeator(IdeatorBase):
    """Generate concepts using Google Gemini (text model)."""

    def __init__(self, settings):
        self.api_keys = settings.google_api_keys
        # Use Gemini 2.0 Flash for text generation
        self.model_name = "gemini-2.0-flash"
        if self.api_keys and GENAI_AVAILABLE:
            genai.configure(api_key=self.api_keys[0])
            self.model = genai.GenerativeModel(self.model_name)
        else:
            self.model = None

    def get_name(self) -> str:
        return "Gemini"

    def is_available(self) -> bool:
        return self.model is not None and GENAI_AVAILABLE

    def generate_concepts(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> list[dict]:
        if not self.is_available():
            return []

        prompt = self._build_concepts_prompt(titles, used_ideas, script, favorites_context, num_concepts)

        try:
            response = self.model.generate_content(prompt)
            text = response.text
            concepts = self._parse_concepts(text)
            # Tag concepts with source
            for c in concepts:
                c['source_llm'] = 'gemini'
            return concepts
        except Exception as e:
            print(f"Gemini error: {e}")
            return []


class MultiLLMIdeator:
    """
    Generate concepts using multiple LLMs in parallel for maximum diversity.

    Combines ideas from Claude, ChatGPT, and Gemini to get different creative
    perspectives on the same video content.
    """

    def __init__(self, settings):
        self.settings = settings
        self.ideators = {}

        # Initialize available ideators
        self.ideators['claude'] = ClaudeIdeatorV2(settings)

        chatgpt = ChatGPTIdeator(settings)
        if chatgpt.is_available():
            self.ideators['chatgpt'] = chatgpt

        gemini = GeminiIdeator(settings)
        if gemini.is_available():
            self.ideators['gemini'] = gemini

    def get_available_llms(self) -> list[str]:
        """Get list of available LLM names."""
        return list(self.ideators.keys())

    def generate_concepts_parallel(
        self,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        concepts_per_llm: int = 10,
        selected_llms: list[str] = None,
        progress_callback=None
    ) -> dict:
        """
        Generate concepts using multiple LLMs in parallel.

        Args:
            titles: Video titles
            used_ideas: Ideas to avoid
            script: Optional video script
            favorites_context: Successful examples context
            concepts_per_llm: Number of concepts each LLM should generate
            selected_llms: Which LLMs to use (None = all available)
            progress_callback: Optional callback(llm_name, status, concepts) for progress updates

        Returns:
            Dict with 'concepts' (all combined), 'by_llm' (grouped by source), 'stats'
        """
        llms_to_use = selected_llms if selected_llms else list(self.ideators.keys())
        llms_to_use = [llm for llm in llms_to_use if llm in self.ideators]

        if not llms_to_use:
            return {'concepts': [], 'by_llm': {}, 'stats': {'error': 'No LLMs available'}}

        results = {}
        all_concepts = []

        def generate_with_llm(llm_name):
            """Worker function for parallel execution."""
            ideator = self.ideators[llm_name]
            if progress_callback:
                progress_callback(llm_name, 'generating', None)

            concepts = ideator.generate_concepts(
                titles=titles,
                used_ideas=used_ideas,
                script=script,
                favorites_context=favorites_context,
                num_concepts=concepts_per_llm
            )

            if progress_callback:
                progress_callback(llm_name, 'complete', concepts)

            return llm_name, concepts

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=len(llms_to_use)) as executor:
            futures = [executor.submit(generate_with_llm, llm) for llm in llms_to_use]

            for future in as_completed(futures):
                try:
                    llm_name, concepts = future.result()
                except Exception as e:
                    print(f"[MULTI-IDEATION] Future failed: {e}")
                    continue
                results[llm_name] = concepts
                all_concepts.extend(concepts)

        # Deduplicate by concept name (keep first occurrence)
        seen_names = set()
        unique_concepts = []
        for concept in all_concepts:
            name = concept.get('concept_name', '').lower()
            if name not in seen_names:
                seen_names.add(name)
                unique_concepts.append(concept)

        return {
            'concepts': unique_concepts,
            'by_llm': results,
            'stats': {
                'total_raw': len(all_concepts),
                'total_unique': len(unique_concepts),
                'by_source': {llm: len(concepts) for llm, concepts in results.items()}
            }
        }

    def generate_with_single_llm(
        self,
        llm_name: str,
        titles: list[str],
        used_ideas: list[str],
        script: str = None,
        favorites_context: str = "",
        num_concepts: int = 10
    ) -> list[dict]:
        """Generate concepts with a specific LLM."""
        if llm_name not in self.ideators:
            return []
        return self.ideators[llm_name].generate_concepts(
            titles=titles,
            used_ideas=used_ideas,
            script=script,
            favorites_context=favorites_context,
            num_concepts=num_concepts
        )
