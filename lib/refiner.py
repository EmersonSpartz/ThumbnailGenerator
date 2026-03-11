"""
Thumbnail Refiner - Quick iteration on promising thumbnails.

This enables the "conversation with the AI" workflow:
1. See a thumbnail you like
2. Describe what to change ("make it more dramatic", "zoom in on face")
3. Get a new version instantly
4. Repeat until perfect
"""

import anthropic
import json
import re
from typing import Optional


class ThumbnailRefiner:
    """
    Refine thumbnails through natural language iteration.

    Instead of writing full prompts, just say what you want to change
    and Claude will modify the prompt intelligently.
    """

    def __init__(self, settings):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    def refine_prompt(
        self,
        original_prompt: str,
        feedback: str,
        conversation_history: list = None
    ) -> dict:
        """
        Refine a prompt based on natural language feedback.

        Args:
            original_prompt: The image generation prompt that was used
            feedback: What to change (e.g., "make it more dramatic", "add red tones")
            conversation_history: Previous refinements for context

        Returns:
            Dict with new_prompt and explanation
        """
        # Build context from history
        history_context = ""
        if conversation_history:
            history_context = "\n\nPrevious refinements:\n"
            for item in conversation_history[-5:]:  # Last 5 iterations
                history_context += f"- Feedback: {item['feedback']}\n"
                history_context += f"  Result: {item['prompt'][:100]}...\n"

        system_prompt = """You are a thumbnail prompt refinement assistant. Your job is to take an existing image generation prompt and modify it based on user feedback.

Rules:
1. Keep the core concept intact unless explicitly asked to change it
2. Make targeted changes based on the feedback
3. Maintain prompt quality and specificity
4. If feedback is vague, make reasonable creative choices
5. Always output a complete, ready-to-use prompt

Common refinement requests and how to handle them:
- "more dramatic" → increase contrast, add dramatic lighting, intensify expressions
- "zoom in" → change to close-up or extreme close-up framing
- "brighter/darker" → adjust lighting descriptions
- "more contrast" → add high contrast, bold colors
- "different angle" → change camera angle description
- "add [color]" → incorporate that color into the scene
- "less busy" → simplify background, reduce elements
- "more energy" → add dynamic elements, action, movement"""

        user_message = f"""Original prompt:
{original_prompt}

{history_context}

User feedback: "{feedback}"

Provide:
1. The refined prompt (complete, ready to use)
2. Brief explanation of what you changed

Return as JSON:
```json
{{
  "refined_prompt": "the complete new prompt",
  "changes_made": "brief explanation of changes"
}}
```"""

        with self.client.messages.stream(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": user_message}
            ],
            system=system_prompt
        ) as stream:
            response = stream.get_final_message()

        # Parse response
        text = response.content[0].text

        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(text)

            return {
                "success": True,
                "new_prompt": data.get("refined_prompt", original_prompt),
                "changes": data.get("changes_made", ""),
                "original_prompt": original_prompt,
                "feedback": feedback
            }
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract the prompt directly
            return {
                "success": True,
                "new_prompt": text.strip(),
                "changes": "Refined based on feedback",
                "original_prompt": original_prompt,
                "feedback": feedback
            }

    def suggest_refinements(self, prompt: str, concept: str = "") -> list[str]:
        """
        Suggest possible refinements for a thumbnail.

        Returns a list of quick suggestions the user can click.
        """
        suggestions = [
            "Make it more dramatic",
            "Zoom in closer",
            "Add more contrast",
            "Make colors more vibrant",
            "Simplify the background",
            "Add more energy/movement",
            "Make lighting more cinematic",
            "Try a different angle",
        ]

        # Add context-specific suggestions based on prompt content
        prompt_lower = prompt.lower()

        if "person" in prompt_lower or "portrait" in prompt_lower or "face" in prompt_lower:
            suggestions.extend([
                "More intense expression",
                "Add eye contact with viewer",
                "Extreme close-up on face",
            ])

        if "tech" in prompt_lower or "ai" in prompt_lower or "computer" in prompt_lower:
            suggestions.extend([
                "More futuristic feel",
                "Add glowing elements",
                "Cooler blue tones",
            ])

        return suggestions[:8]  # Return top 8 suggestions


class IterationSession:
    """
    Manages an iteration session for refining a single thumbnail concept.

    Tracks the history of changes so you can:
    - Go back to previous versions
    - See what changes were made
    - Build on successful directions
    """

    def __init__(self, original_prompt: str, original_image_path: str = None):
        self.original_prompt = original_prompt
        self.original_image_path = original_image_path
        self.history = []
        self.current_index = -1

    def add_iteration(
        self,
        prompt: str,
        image_path: str,
        feedback: str,
        changes: str
    ):
        """Add a new iteration to the session."""
        # If we're not at the end, truncate future history
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]

        self.history.append({
            "prompt": prompt,
            "image_path": image_path,
            "feedback": feedback,
            "changes": changes,
            "index": len(self.history)
        })
        self.current_index = len(self.history) - 1

    def get_current(self) -> Optional[dict]:
        """Get the current iteration."""
        if self.current_index >= 0 and self.current_index < len(self.history):
            return self.history[self.current_index]
        return None

    def go_back(self) -> Optional[dict]:
        """Go back to the previous iteration."""
        if self.current_index > 0:
            self.current_index -= 1
            return self.history[self.current_index]
        return None

    def go_forward(self) -> Optional[dict]:
        """Go forward to the next iteration."""
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            return self.history[self.current_index]
        return None

    def get_prompt_for_refinement(self) -> str:
        """Get the current prompt to refine."""
        current = self.get_current()
        if current:
            return current["prompt"]
        return self.original_prompt

    def get_conversation_history(self) -> list:
        """Get history for context in refinement."""
        return [
            {"feedback": h["feedback"], "prompt": h["prompt"]}
            for h in self.history
        ]

    def to_dict(self) -> dict:
        """Serialize session for storage."""
        return {
            "original_prompt": self.original_prompt,
            "original_image_path": self.original_image_path,
            "history": self.history,
            "current_index": self.current_index
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'IterationSession':
        """Restore session from storage."""
        session = cls(
            original_prompt=data["original_prompt"],
            original_image_path=data.get("original_image_path")
        )
        session.history = data.get("history", [])
        session.current_index = data.get("current_index", -1)
        return session
