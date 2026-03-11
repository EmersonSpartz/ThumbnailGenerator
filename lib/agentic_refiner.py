"""
Agentic Image Refinement - Iteratively improve thumbnail quality.

Uses Claude to evaluate generated thumbnails and refine prompts in a loop
until quality standards are met. Based on the agentic image generation pattern
popularized in 2026.

Quality criteria for Species channel thumbnails:
- Premium, non-clickbait aesthetic
- Clear, compelling visual hierarchy
- Professional composition
- Appropriate for educational/scientific content
"""

import os
import json
import base64
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor
import anthropic


class AgenticImageRefiner:
    """
    Iteratively refine thumbnail generation prompts using Claude's analysis.

    Flow:
    1. Generate initial thumbnails
    2. Claude evaluates quality (0-10 score)
    3. If below threshold, Claude suggests prompt improvements
    4. Regenerate with refined prompts
    5. Repeat until quality threshold met (or max iterations reached)
    """

    def __init__(self, settings, max_iterations: int = 3, quality_threshold: float = 8.0):
        self.settings = settings
        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        self.api_key = os.getenv('ANTHROPIC_API_KEY', '')
        # Use Opus 4.6 for best quality evaluation and refinement
        self.model = 'claude-opus-4-6'

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.client = anthropic.Anthropic(api_key=self.api_key, max_retries=3)

        # Load rubric from file for easy editing
        rubric_path = Path(__file__).parent.parent / 'rubric.txt'
        try:
            with open(rubric_path, 'r') as f:
                self.rubric = f.read()
        except FileNotFoundError:
            # Fallback to default if file doesn't exist
            self.rubric = self._get_default_rubric()

    def encode_image(self, image_path: Path) -> str:
        """Encode image to base64 for Claude API."""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def evaluate_thumbnails_batch(self, images_data: List[Dict]) -> List[Dict]:
        """
        Evaluate multiple thumbnails in a single API call for maximum speed.

        Args:
            images_data: List of {image_path, prompt_used, concept_name, model}

        Returns:
            List of evaluation dicts
        """
        if not images_data:
            return []

        # Build content array with all images - filter out missing files first
        valid_images = []
        content = []

        for img_data in images_data:
            image_path = img_data['image_path']
            if not image_path.exists():
                print(f"[AGENTIC WARN] Image not found, skipping: {image_path}")
                continue
            valid_images.append(img_data)

            ext = image_path.suffix.lower()
            media_type_map = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            media_type = media_type_map.get(ext, 'image/jpeg')

            image_data = self.encode_image(image_path)

            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data
                }
            })

        if not valid_images:
            return []

        # Build evaluation prompt only for valid images (synced with content array)
        prompt_parts = [f"Evaluate these {len(valid_images)} YouTube thumbnails for the Species channel.\n"]

        for idx, img_data in enumerate(valid_images):
            prompt_parts.append(f"\n**Image {idx+1}** ({img_data['model']})")
            prompt_parts.append(f"Concept: {img_data['concept_name']}")
            prompt_parts.append(f"Prompt: {img_data['prompt_used']}\n")

        prompt_parts.append(self.rubric)
        prompt_parts.append("""

Respond with JSON array:
[
  {"image": 1, "score": <float>, "analysis": "<Specific: Which criteria scored low? What exact elements work/fail?>", "refined_prompt": "<If <8: Add specific fixes like 'more contrast', 'wider shot', 'add mysterious element', etc.>"},
  ...
]""")

        evaluation_prompt = "\n".join(prompt_parts)
        content.append({"type": "text", "text": evaluation_prompt})

        try:
            print(f"[AGENTIC] Evaluating {len(images_data)} images with Claude Opus 4.6...")
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4000,
                timeout=120.0,
                messages=[{"role": "user", "content": content}]
            ) as stream:
                response = stream.get_final_message()
            print(f"[AGENTIC] Evaluation complete, parsing response...")

            response_text = response.content[0].text

            # Extract JSON
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            results = json.loads(response_text)

            # Match results back to valid images (synced indices)
            evaluations = []
            for idx, img_data in enumerate(valid_images):
                if idx < len(results):
                    result = results[idx]
                    evaluations.append({
                        "score": result.get("score", 5.0),
                        "analysis": result.get("analysis", ""),
                        "refined_prompt": result.get("refined_prompt", img_data['prompt_used']),
                        "model": img_data['model']
                    })
                else:
                    # Fallback if response is incomplete
                    evaluations.append({
                        "score": 6.0,
                        "analysis": "Evaluation incomplete",
                        "refined_prompt": img_data['prompt_used'],
                        "model": img_data['model']
                    })

            return evaluations

        except Exception as e:
            print(f"[AGENTIC ERROR] Evaluation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return default evaluations on error
            return [{
                "score": 6.0,
                "analysis": f"Error evaluating: {str(e)}",
                "refined_prompt": images_data[i]['prompt_used'] if i < len(images_data) else '',
                "model": images_data[i]['model'] if i < len(images_data) else 'unknown'
            } for i in range(len(images_data))]

    def evaluate_thumbnail(self, image_path: Path, prompt_used: str, concept_name: str) -> Dict:
        """
        Have Claude evaluate a thumbnail's quality.

        Returns:
            {
                "score": float (0-10),
                "analysis": str (what works, what doesn't),
                "refined_prompt": str (improved version if score < threshold)
            }
        """
        if not image_path.exists():
            return {"score": 0, "analysis": "Image file not found", "refined_prompt": prompt_used}

        # Determine image media type
        ext = image_path.suffix.lower()
        media_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        media_type = media_type_map.get(ext, 'image/jpeg')

        image_data = self.encode_image(image_path)

        evaluation_prompt = f"""Evaluate this YouTube thumbnail for the Species channel (educational nature content).

**Concept**: {concept_name}
**Prompt used**: {prompt_used}

{self.rubric}

Provide your response as JSON:
{{
    "score": <float 0-10>,
    "analysis": "<Specific: Which criteria scored low? What exact elements work/fail?>",
    "refined_prompt": "<If score < 8: Add specific fixes like 'more contrast', 'add mysterious element', 'wider shot', etc.>"
}}"""

        try:
            print(f"[AGENTIC] Evaluating single thumbnail: {concept_name}")
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2000,
                timeout=120.0,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": evaluation_prompt
                        }
                    ]
                }]
            ) as stream:
                response = stream.get_final_message()

            # Parse Claude's response
            response_text = response.content[0].text

            # Try to extract JSON from response
            # Claude might wrap it in markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)

            # Ensure required fields
            if "score" not in result:
                result["score"] = 5.0
            if "analysis" not in result:
                result["analysis"] = "No analysis provided"
            if "refined_prompt" not in result:
                result["refined_prompt"] = prompt_used

            return result

        except Exception as e:
            return {
                "score": 5.0,
                "analysis": f"Error evaluating thumbnail: {str(e)}",
                "refined_prompt": prompt_used
            }

    def refine_prompt_batch(self, evaluations: List[Dict], original_prompt_data: dict) -> dict:
        """
        Given multiple evaluations (from different models), synthesize the best refinements.

        Args:
            evaluations: List of evaluation dicts from evaluate_thumbnail()
            original_prompt_data: The original prompt data dict

        Returns:
            Refined prompt_data dict with improved prompt
        """
        # Calculate average score (for informational purposes)
        scores = [e["score"] for e in evaluations if "score" in e]
        avg_score = sum(scores) / len(scores) if scores else 5.0

        # Always refine - synthesize all refined prompts and analyses
        synthesis_prompt = f"""Multiple AI models generated thumbnails for: "{original_prompt_data.get('concept_name', '')}"

**Original prompt**: {original_prompt_data.get('prompt', '')}

**Evaluations from different models**:
"""
        for i, eval_data in enumerate(evaluations):
            synthesis_prompt += f"\n{i+1}. Score: {eval_data.get('score', 'N/A')}/10\n"
            synthesis_prompt += f"   Analysis: {eval_data.get('analysis', 'N/A')}\n"
            synthesis_prompt += f"   Suggested prompt: {eval_data.get('refined_prompt', 'N/A')}\n"

        synthesis_prompt += """
Based on these evaluations, create ONE dramatically improved prompt that addresses ALL issues identified.

**CRITICAL**: Make BOLD, SPECIFIC changes to create visually striking improvements:
- If composition is weak, specify exact camera angles/framing (e.g., "extreme close-up", "dramatic low angle")
- If colors lack impact, demand specific bold palettes (e.g., "vibrant orange-red glow", "deep purple shadows with cyan highlights")
- If lighting is flat, specify dramatic lighting (e.g., "backlit with rim lighting", "chiaroscuro lighting")
- If subject is boring, add specific compelling elements (e.g., "mysterious glowing veins", "fractured glass effect")
- Make changes that will create OBVIOUS visual improvements, not subtle tweaks

Return ONLY the dramatically improved prompt text, no JSON, no explanation."""

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=1000,
                timeout=90.0,
                messages=[{
                    "role": "user",
                    "content": synthesis_prompt
                }]
            ) as stream:
                response = stream.get_final_message()

            refined_prompt = response.content[0].text.strip()

            # Remove any quotes if present
            refined_prompt = refined_prompt.strip('"\'')

            # Create refined prompt_data
            refined_data = original_prompt_data.copy()
            refined_data['prompt'] = refined_prompt
            refined_data['refinement_iteration'] = original_prompt_data.get('refinement_iteration', 0) + 1

            return refined_data

        except Exception as e:
            # If synthesis fails, just return original
            return original_prompt_data

    def should_refine(self, evaluations: List[Dict]) -> bool:
        """Check if we should do another refinement iteration."""
        scores = [e["score"] for e in evaluations if "score" in e]
        if not scores:
            return False

        avg_score = sum(scores) / len(scores)
        return avg_score < self.quality_threshold

    def get_refinement_summary(self, all_iterations: List[Dict]) -> str:
        """Generate a summary of the refinement process."""
        summary = f"Agentic refinement completed in {len(all_iterations)} iterations:\n\n"

        for i, iteration in enumerate(all_iterations):
            scores = [e["score"] for e in iteration["evaluations"] if "score" in e]
            avg_score = sum(scores) / len(scores) if scores else 0

            summary += f"Iteration {i+1}: Avg score {avg_score:.1f}/10\n"
            if i < len(all_iterations) - 1:
                summary += f"  → Refined prompt and regenerated\n"
            else:
                if avg_score >= self.quality_threshold:
                    summary += f"  ✓ Quality threshold met!\n"
                else:
                    summary += f"  → Max iterations reached\n"

        return summary

    def _get_default_rubric(self) -> str:
        """Fallback rubric if rubric.txt doesn't exist."""
        return """**Quality criteria** (Research-based YouTube CTR optimization):

**1. SCROLL-STOPPING POWER (0-3 points)** 🎯 MOST IMPORTANT
- Bold, high-contrast colors (yellows/oranges proven +20-30% CTR)
- Clear visual hierarchy - one obvious focal point
- "Moment of awe" - intriguing/mysterious element that sparks curiosity
- Readable at mobile thumbnail size (320x180px)
Score: 3=instant attention grab, 2=noticeable, 1=blends in, 0=invisible

**2. EMOTIONAL HOOK (0-2 points)** - Proven CTR driver
- Visible emotion/expression if face present (confusion, awe, concern)
- OR mysterious object/scene that creates questions
- Veritasium framework: High info gap + low misleading = ideal
- Creates "I need to know" feeling in 1 second
Score: 2=strong curiosity, 1=mild interest, 0=no hook

**3. VISUAL EXECUTION (0-2 points)**
- Sharp, professional quality (not blurry/low-res)
- Clean composition - subject fills frame, uncluttered
- Natural color grading (not oversaturated/artificial)
- BBC/NatGeo/Kurzgesagt aesthetic for educational content
Score: 2=professional, 1=acceptable, 0=amateur

**4. TEXT (0-2 points)** - If text present
- Under 12 characters (proven best practice)
- High contrast, readable at small size
- Adds value (not redundant with visuals)
Score: 2=perfect text, 1=okay, 0=bad/too much, N/A=no text (fine)

**5. THUMBNAIL-SPECIFIC (0-1 point)**
- Works at actual YouTube size (not just full-screen)
- Distinct from similar videos (not generic)
- Clear what video is about WITHOUT title
Score: 1=yes, 0=no

**SCORE 0-10**. Research shows: 5-7 is typical AI output, 8+ is top-tier."""
