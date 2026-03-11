"""
Image Generator - Generate thumbnails using multiple AI models.

Supports:
- Gemini (NanoBanana Pro, Flash)
- Replicate models (Flux, SDXL)
- Ideogram (great for text in images)
"""

import os
import time
import base64
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from abc import ABC, abstractmethod

# Google Generative AI
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# Replicate (for Flux, SDXL, etc.)
try:
    import replicate
    REPLICATE_AVAILABLE = True
except ImportError:
    REPLICATE_AVAILABLE = False

# Requests for direct API calls
import requests


class ImageGeneratorBase(ABC):
    """Base class for image generators."""

    @abstractmethod
    def generate(self, prompt: str, output_path: Path) -> dict:
        """Generate an image from a prompt."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this generator."""
        pass


class GeminiImageGenerator(ImageGeneratorBase):
    """Generate images using Google's Gemini models."""

    def __init__(self, settings, model_key: str = "nanobanana"):
        self.settings = settings
        self.api_keys = settings.google_api_keys
        self.current_key_index = 0
        self.output_dir = settings.output_dir

        # Model options
        self.models = {
            "nanobanana": "gemini-3-pro-image-preview",  # NanoBanana Pro (Gemini 3 Pro Image)
            "nanobanana2": "gemini-3.1-flash-image-preview",  # NanoBanana 2 Pro (Pro quality at Flash speed)
            "flash": "gemini-2.5-flash-image",  # Nano Banana standard (faster, good quality)
        }
        self.model_key = model_key
        self._configure_client()

    def _configure_client(self):
        """Configure the Gemini client with current API key."""
        if self.api_keys and GENAI_AVAILABLE:
            genai.configure(api_key=self.api_keys[self.current_key_index])

    def _rotate_key(self):
        """Rotate to the next API key."""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            self._configure_client()
            return True
        return False

    def set_model(self, model_key: str):
        """Set which model to use."""
        if model_key in self.models:
            self.model_key = model_key

    def get_name(self) -> str:
        return f"Gemini ({self.model_key})"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """
        Generate an image from prompt data.

        Args:
            prompt_data: Dict containing 'prompt', 'concept_name', etc.
            batch_id: Optional batch identifier for organizing output

        Returns:
            Dict with 'success', 'file_path', 'error', etc.
        """
        if not GENAI_AVAILABLE:
            return {"success": False, "error": "google-generativeai not installed"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        # Create filename - Gemini returns JPEG images
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.jpg"

        # Determine output path
        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to generate
        max_retries = len(self.api_keys)
        for attempt in range(max_retries):
            try:
                model = genai.GenerativeModel(self.models[self.model_key])

                # Generate image
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        candidate_count=1,
                    )
                )

                # Extract and save image
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            # Data is already bytes, not base64 encoded
                            image_data = part.inline_data.data
                            if isinstance(image_data, str):
                                # If it's a string, it might be base64 encoded
                                image_data = base64.b64decode(image_data)
                            output_path.write_bytes(image_data)
                            return {
                                "success": True,
                                "file_path": str(output_path),
                                "prompt_used": prompt,
                                "concept": prompt_data
                            }

                return {"success": False, "error": "No image in response"}

            except Exception as e:
                error_str = str(e)
                if "quota" in error_str.lower() or "rate" in error_str.lower():
                    if self._rotate_key():
                        continue
                    return {"success": False, "error": "All API keys exhausted", "quota_exhausted": True}
                # Retry once on transient network errors
                if attempt == 0 and any(t in error_str.lower() for t in ["timeout", "connection", "503", "502", "500"]):
                    time.sleep(2)
                    continue
                return {"success": False, "error": error_str}

        return {"success": False, "error": "All retries failed"}

    def get_key_status(self) -> dict:
        """Get status of API keys."""
        return {
            "total_keys": len(self.api_keys),
            "current_key": self.current_key_index + 1,
            "model": self.model_key
        }


class ReplicateImageGenerator(ImageGeneratorBase):
    """Generate images using Replicate-hosted models (Flux, SDXL, etc.)."""

    def __init__(self, settings, model_name: str = "flux-schnell"):
        self.settings = settings
        self.output_dir = settings.output_dir

        # Available models on Replicate
        # Standard models
        self.models = {
            "flux-schnell": "black-forest-labs/flux-schnell",
            "flux-dev": "black-forest-labs/flux-dev",
            "flux-pro": "black-forest-labs/flux-1.1-pro",
            "sdxl": "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            "sdxl-lightning": "bytedance/sdxl-lightning-4step:5f24084160c9089501c1b3545d9be3c27883ae2239b6f412990e82d4a6210f8f",
            # YOUR custom AI Species model - trained on your channel's thumbnails!
            "aispecies": "emersonspartz/aispecies-thumbnails:a442d2b1bdd2e349f3ee2ebcdbfcaaf45558308bdf2916ae96ec61744973d8bc",
            # Flux Thumbnails LoRA - fine-tuned on YouTube thumbnails
            "flux-thumbnails": "justmalhar/flux-thumbnails-v2",
        }
        self.model_name = model_name

        # Trigger words for fine-tuned models
        self.trigger_words = {
            "aispecies": "AISPECIES",
            "flux-thumbnails": "YTTHUMBNAIL",
        }

        # Set API token from environment
        self.api_token = os.getenv('REPLICATE_API_TOKEN', '')

    def set_model(self, model_name: str):
        """Set which model to use."""
        if model_name in self.models:
            self.model_name = model_name

    def get_name(self) -> str:
        return f"Replicate ({self.model_name})"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using Replicate."""
        if not REPLICATE_AVAILABLE:
            return {"success": False, "error": "replicate not installed"}

        if not self.api_token:
            return {"success": False, "error": "REPLICATE_API_TOKEN not set"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        # Determine output path
        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            try:
                # Run the model
                model_id = self.models.get(self.model_name, self.models["flux-schnell"])

                # Add trigger word if this is a fine-tuned model
                actual_prompt = prompt
                if self.model_name in self.trigger_words:
                    trigger = self.trigger_words[self.model_name]
                    if trigger not in prompt:
                        # Prepend trigger word for thumbnail style
                        actual_prompt = f"a youtube thumbnail in the style of {trigger}, {prompt}"

                # Flux thumbnail LoRA model - optimized settings
                if self.model_name == "flux-thumbnails":
                    input_params = {
                        "prompt": actual_prompt,
                        "num_outputs": 1,
                        "aspect_ratio": "16:9",  # YouTube thumbnail ratio
                        "output_format": "png",
                        "guidance_scale": 3,  # Recommended: 2-3.5
                        "num_inference_steps": 28,  # Recommended for dev mode
                    }
                # Standard Flux models
                elif "flux" in self.model_name:
                    input_params = {
                        "prompt": actual_prompt,
                        "num_outputs": 1,
                        "aspect_ratio": "16:9",  # YouTube thumbnail ratio
                        "output_format": "png",
                    }
                else:
                    # SDXL-style models
                    input_params = {
                        "prompt": actual_prompt,
                        "width": 1280,
                        "height": 720,
                        "num_outputs": 1,
                    }

                output = replicate.run(model_id, input=input_params)

                # Download the image
                if output:
                    image_url = output[0] if isinstance(output, list) else output
                    response = requests.get(image_url)
                    if response.status_code == 200:
                        output_path.write_bytes(response.content)
                        return {
                            "success": True,
                            "file_path": str(output_path),
                            "prompt_used": prompt,
                            "concept": prompt_data,
                            "model": self.model_name
                        }

                return {"success": False, "error": "No output from model"}

            except Exception as e:
                error_str = str(e)
                if attempt == 0 and any(t in error_str.lower() for t in ["timeout", "connection", "503", "502", "500"]):
                    time.sleep(2)
                    continue
                return {"success": False, "error": error_str}


class MidjourneyGenerator(ImageGeneratorBase):
    """
    Generate images using Midjourney via LegNext.ai API.
    Midjourney produces high-quality artistic images - great for eye-catching thumbnails.

    Requires LEGNEXT_API_KEY in .env file.
    Get your API key at: https://legnext.ai/
    Pricing: $30/month for 30,000 API points (or 200 free points to try)
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('LEGNEXT_API_KEY', '')
        self.api_url = "https://api.legnext.ai/api/v1/diffusion"
        self.status_url = "https://api.legnext.ai/api/v1/job/"  # Note: singular "job" not "jobs"

    def get_name(self) -> str:
        return "Midjourney"

    def _wait_for_result(self, job_id: str, max_wait: int = 300) -> dict:
        """Poll for task completion."""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{self.status_url}{job_id}", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "completed" or status == "success":
                        # Get the image URL from the result - LegNext format
                        output = data.get("output", {})
                        image_url = output.get("image_url")
                        # Also check image_urls array (LegNext returns 4 variations)
                        if not image_url:
                            image_urls = output.get("image_urls", [])
                            if image_urls:
                                image_url = image_urls[0]  # Take first variation

                        if image_url:
                            return {"success": True, "image_url": image_url}
                        return {"success": False, "error": f"No image URL in response: {data}"}

                    elif status == "failed" or status == "error":
                        error = data.get("error", data.get("message", "Unknown error"))
                        return {"success": False, "error": f"Task failed: {error}"}

                    # Still processing, wait and retry
                    time.sleep(5)
                else:
                    return {"success": False, "error": f"Fetch error: {response.status_code} - {response.text}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Timeout waiting for image"}

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using Midjourney via LegNext.ai."""
        if not self.api_key:
            return {"success": False, "error": "LEGNEXT_API_KEY not set. Get one at https://legnext.ai/"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        # Determine output path
        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }

            # Add Midjourney params to prompt (aspect ratio, version)
            mj_prompt = f"{prompt} --ar 16:9 --v 7"

            payload = {
                "text": mj_prompt
            }

            response = requests.post(self.api_url, headers=headers, json=payload)

            if response.status_code in [200, 201, 202]:
                data = response.json()
                job_id = data.get("job_id") or data.get("id") or data.get("task_id")

                if job_id:
                    # Wait for the image to be generated
                    result = self._wait_for_result(job_id)

                    if result.get("success"):
                        # Download the image
                        img_response = requests.get(result["image_url"])
                        if img_response.status_code == 200:
                            output_path.write_bytes(img_response.content)
                            return {
                                "success": True,
                                "file_path": str(output_path),
                                "prompt_used": mj_prompt,
                                "concept": prompt_data,
                                "model": "midjourney"
                            }
                        return {"success": False, "error": f"Failed to download image: {img_response.status_code}"}
                    return result

                # Maybe the image was returned directly?
                image_url = data.get("url") or data.get("image_url")
                if image_url:
                    img_response = requests.get(image_url)
                    if img_response.status_code == 200:
                        output_path.write_bytes(img_response.content)
                        return {
                            "success": True,
                            "file_path": str(output_path),
                            "prompt_used": mj_prompt,
                            "concept": prompt_data,
                            "model": "midjourney"
                        }

                return {"success": False, "error": f"No job_id in response: {data}"}

            return {"success": False, "error": f"API error: {response.status_code} - {response.text}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class IdeogramGenerator(ImageGeneratorBase):
    """
    Generate images using Ideogram API.
    Ideogram is particularly good at rendering text in images - useful for thumbnails!
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('IDEOGRAM_API_KEY', '')
        self.api_url = "https://api.ideogram.ai/generate"

    def get_name(self) -> str:
        return "Ideogram"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using Ideogram."""
        if not self.api_key:
            return {"success": False, "error": "IDEOGRAM_API_KEY not set"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        # Determine output path
        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            headers = {
                "Api-Key": self.api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "image_request": {
                    "prompt": prompt,
                    "aspect_ratio": "ASPECT_16_9",  # YouTube thumbnail
                    "model": "V_2",  # Latest model
                    "magic_prompt_option": "AUTO"
                }
            }

            response = requests.post(self.api_url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    image_url = data["data"][0].get("url")
                    if image_url:
                        img_response = requests.get(image_url)
                        if img_response.status_code == 200:
                            output_path.write_bytes(img_response.content)
                            return {
                                "success": True,
                                "file_path": str(output_path),
                                "prompt_used": prompt,
                                "concept": prompt_data,
                                "model": "ideogram"
                            }

            return {"success": False, "error": f"API error: {response.status_code}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class PikzelsGenerator(ImageGeneratorBase):
    """
    Generate thumbnails using Pikzels API - models trained specifically on YouTube thumbnails.
    Uses pkz-2 (most versatile, best photorealism).

    Requires PIKZELS_API_KEY in .env file.
    Get your API key at: https://pikzels.com
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('PIKZELS_API_KEY', '')
        self.api_url = "https://api.pikzels.com/v1/thumbnail"

    def get_name(self) -> str:
        return "Pikzels"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate a thumbnail using Pikzels."""
        if not self.api_key:
            return {"success": False, "error": "PIKZELS_API_KEY not set. Get one at https://pikzels.com"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            headers = {
                "X-Api-Key": self.api_key,
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": prompt,
                "model": "pkz-2",
                "aspect_ratio": "16:9",
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                data = response.json()
                # Try various response formats
                image_url = (data.get("image_url") or data.get("url")
                             or data.get("data", {}).get("image_url")
                             or data.get("output", {}).get("image_url"))

                if image_url:
                    img_response = requests.get(image_url, timeout=60)
                    if img_response.status_code == 200:
                        output_path.write_bytes(img_response.content)
                        return {
                            "success": True,
                            "file_path": str(output_path),
                            "prompt_used": prompt,
                            "concept": prompt_data,
                            "model": "pikzels"
                        }

                # Maybe base64 data directly
                b64_data = data.get("image") or data.get("b64_json") or data.get("data", {}).get("b64_json")
                if b64_data:
                    image_data = base64.b64decode(b64_data)
                    output_path.write_bytes(image_data)
                    return {
                        "success": True,
                        "file_path": str(output_path),
                        "prompt_used": prompt,
                        "concept": prompt_data,
                        "model": "pikzels"
                    }

                return {"success": False, "error": f"No image in response: {list(data.keys())}"}

            return {"success": False, "error": f"API error: {response.status_code} - {response.text[:200]}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class GPTImageGenerator(ImageGeneratorBase):
    """
    Generate images using OpenAI's GPT Image model.
    Currently the #1 rated image generation model overall.

    Requires OPENAI_API_KEY in .env file.
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('OPENAI_API_KEY', '')

    def get_name(self) -> str:
        return "GPT Image"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using OpenAI GPT Image."""
        if not self.api_key:
            return {"success": False, "error": "OPENAI_API_KEY not set"}

        try:
            from openai import OpenAI
        except ImportError:
            return {"success": False, "error": "openai package not installed. Run: pip install openai"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            client = OpenAI(api_key=self.api_key)

            result = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                n=1,
                size="1536x1024",
                quality="high",
            )

            # gpt-image-1 always returns base64 (no URL option)
            image_data = result.data[0]
            b64 = getattr(image_data, 'b64_json', None)
            if b64:
                img_bytes = base64.b64decode(b64)
                output_path.write_bytes(img_bytes)
            else:
                return {"success": False, "error": "No image data in response"}

            return {
                "success": True,
                "file_path": str(output_path),
                "prompt_used": prompt,
                "concept": prompt_data,
                "model": "gpt-image"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class RecraftGenerator(ImageGeneratorBase):
    """
    Generate images using Recraft V3 API.
    Excellent for design-quality images with clean typography and premium aesthetic.

    Requires RECRAFT_API_TOKEN in .env file.
    Get your API key at: https://www.recraft.ai
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('RECRAFT_API_TOKEN', '')
        self.api_url = "https://external.api.recraft.ai/v1/images/generations"

    def get_name(self) -> str:
        return "Recraft V3"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using Recraft V3."""
        if not self.api_key:
            return {"success": False, "error": "RECRAFT_API_TOKEN not set. Get one at https://www.recraft.ai"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": prompt,
                "style": "realistic_image",
                "model": "recraftv3",
                "size": "1820x1024",
                "response_format": "url"
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                data = response.json()
                images = data.get("data", [])
                if images and images[0].get("url"):
                    img_response = requests.get(images[0]["url"], timeout=60)
                    if img_response.status_code == 200:
                        output_path.write_bytes(img_response.content)
                        return {
                            "success": True,
                            "file_path": str(output_path),
                            "prompt_used": prompt,
                            "concept": prompt_data,
                            "model": "recraft"
                        }

                # Try b64_json format
                if images and images[0].get("b64_json"):
                    img_bytes = base64.b64decode(images[0]["b64_json"])
                    output_path.write_bytes(img_bytes)
                    return {
                        "success": True,
                        "file_path": str(output_path),
                        "prompt_used": prompt,
                        "concept": prompt_data,
                        "model": "recraft"
                    }

                return {"success": False, "error": f"No image in response: {data}"}

            return {"success": False, "error": f"API error: {response.status_code} - {response.text[:200]}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class TogetherFluxGenerator(ImageGeneratorBase):
    """
    Generate images using Together.ai's Flux Schnell (FREE tier).
    Great for fast draft thumbnails at zero cost.

    Requires TOGETHER_API_KEY in .env file.
    Get your API key at: https://www.together.ai
    """

    def __init__(self, settings):
        self.settings = settings
        self.output_dir = settings.output_dir
        self.api_key = os.getenv('TOGETHER_API_KEY', '')
        self.api_url = "https://api.together.xyz/v1/images/generations"

    def get_name(self) -> str:
        return "Together Flux"

    def generate(self, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate an image using Together.ai Flux Schnell (free)."""
        if not self.api_key:
            return {"success": False, "error": "TOGETHER_API_KEY not set. Get one free at https://www.together.ai"}

        prompt = prompt_data.get('prompt', '')
        concept_name = prompt_data.get('concept_name', 'untitled')

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in concept_name)[:30]
        filename = f"{timestamp}_{safe_name}.png"

        if batch_id:
            output_path = self.output_dir / batch_id / filename
        else:
            output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": prompt,
                "width": 1280,
                "height": 720,
                "steps": 4,
                "n": 1,
                "response_format": "b64_json"
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)

            if response.status_code == 200:
                data = response.json()
                images = data.get("data", [])
                if images:
                    b64_data = images[0].get("b64_json")
                    if b64_data:
                        img_bytes = base64.b64decode(b64_data)
                        output_path.write_bytes(img_bytes)
                        return {
                            "success": True,
                            "file_path": str(output_path),
                            "prompt_used": prompt,
                            "concept": prompt_data,
                            "model": "together-flux"
                        }

                    image_url = images[0].get("url")
                    if image_url:
                        img_response = requests.get(image_url, timeout=60)
                        if img_response.status_code == 200:
                            output_path.write_bytes(img_response.content)
                            return {
                                "success": True,
                                "file_path": str(output_path),
                                "prompt_used": prompt,
                                "concept": prompt_data,
                                "model": "together-flux"
                            }

                return {"success": False, "error": f"No image in response: {data}"}

            return {"success": False, "error": f"API error: {response.status_code} - {response.text[:200]}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class MultiModelGenerator:
    """
    Generate thumbnails using multiple models and compare results.
    Useful for finding the best model for your style.

    ADDING MODELS: Register generators here based on available API keys.
    Pattern: if os.getenv('API_KEY'): self.generators["model-id"] = GeneratorClass(settings)
    Each registered model automatically appears in /api/models endpoint.
    """

    def __init__(self, settings):
        self.settings = settings
        self.generators = {}

        # Initialize available generators (auto-registered based on API keys)
        if GENAI_AVAILABLE and settings.google_api_keys:
            self.generators["nanobanana2"] = GeminiImageGenerator(settings, model_key="nanobanana2")

        if REPLICATE_AVAILABLE and os.getenv('REPLICATE_API_TOKEN'):
            self.generators["flux"] = ReplicateImageGenerator(settings, "flux-schnell")
            self.generators["sdxl"] = ReplicateImageGenerator(settings, "sdxl-lightning")
            # YOUR custom AI Species model!
            self.generators["aispecies"] = ReplicateImageGenerator(settings, "aispecies")

        if os.getenv('IDEOGRAM_API_KEY'):
            self.generators["ideogram"] = IdeogramGenerator(settings)

        # Midjourney via LegNext.ai (requires LEGNEXT_API_KEY)
        if os.getenv('LEGNEXT_API_KEY'):
            self.generators["midjourney"] = MidjourneyGenerator(settings)

        # Pikzels - YouTube thumbnail specialist (API not yet public, coming soon)
        # if os.getenv('PIKZELS_API_KEY'):
        #     self.generators["pikzels"] = PikzelsGenerator(settings)

        # Recraft V3 - premium design aesthetic (requires RECRAFT_API_TOKEN)
        if os.getenv('RECRAFT_API_TOKEN'):
            self.generators["recraft"] = RecraftGenerator(settings)


    def get_available_models(self) -> list[str]:
        """Get list of available model names."""
        return list(self.generators.keys())

    def generate_with_all(self, prompt_data: dict, batch_id: str = "") -> dict:
        """
        Generate the same prompt with all available models.
        Returns results from each model for comparison.
        """
        results = {}
        for name, generator in self.generators.items():
            result = generator.generate(prompt_data, f"{batch_id}/{name}" if batch_id else name)
            results[name] = result
            time.sleep(1)  # Small delay between models

        return results

    def generate_with_model(self, model_name: str, prompt_data: dict, batch_id: str = "") -> dict:
        """Generate with a specific model."""
        if model_name not in self.generators:
            return {"success": False, "error": f"Model {model_name} not available"}
        return self.generators[model_name].generate(prompt_data, batch_id)
