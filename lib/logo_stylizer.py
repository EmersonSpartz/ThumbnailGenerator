"""
Stylize composited logos via FLUX Fill Pro inpainting on Replicate.

Takes a thumbnail with static logos already placed, and uses AI inpainting
to transform logo regions based on creative direction (e.g., "dripping blood",
"on fire", "holding a knife").
"""

import os
import tempfile
import requests
import replicate
from pathlib import Path
from PIL import Image, ImageFilter

# Describe the actual icon shape (not the brand name) to avoid text artifacts
LOGO_ICON_DESCRIPTIONS = {
    "openai": "a black hexagonal knot symbol on a circular background",
    "claude": "an orange sunburst/sparkle symbol on a circular background",
    "gemini": "a blue four-pointed star symbol on a circular background",
    "meta": "a blue infinity loop symbol",
    "xai": "a white X symbol on a black circular background",
    "mistral": "an orange geometric symbol on a circular background",
    "deepseek": "a blue whale icon on a white rounded square",
    "perplexity": "a teal abstract symbol on a rounded square",
    "apple": "a black apple silhouette icon",
    "microsoft": "a four-colored square grid icon (red blue yellow green)",
    "nvidia": "a green eye-shaped icon",
    "samsung": "a blue oval icon",
    "cohere": "an abstract coral-colored icon",
}


class LogoStylizer:
    def __init__(self):
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "")
        self.model_id = "black-forest-labs/flux-fill-pro"

    @property
    def available(self) -> bool:
        return bool(self.api_token)

    def generate_mask(self, image_size: tuple, logo_bbox: dict, padding: int = 30) -> Image.Image:
        """
        Create a mask image: black everywhere, white where the logo is.
        Uses soft edges for natural blending.
        """
        w, h = image_size
        mask = Image.new("L", (w, h), 0)

        from PIL import ImageDraw
        draw = ImageDraw.Draw(mask)

        x1 = max(0, logo_bbox["x"] - padding)
        y1 = max(0, logo_bbox["y"] - padding)
        x2 = min(w, logo_bbox["x"] + logo_bbox["width"] + padding)
        y2 = min(h, logo_bbox["y"] + logo_bbox["height"] + padding)

        draw.rectangle([x1, y1, x2, y2], fill=255)

        # Soft edges for natural blending
        mask = mask.filter(ImageFilter.GaussianBlur(8))

        return mask

    def stylize_logo(self, image_path: str, mask: Image.Image, prompt: str, logo_key: str) -> bool:
        """
        Call FLUX Fill Pro to inpaint a single logo region.
        Returns True on success, False on failure. Modifies image in place.
        """
        mask_file = None
        try:
            # Save mask to temp file
            mask_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            mask.save(mask_file.name)

            print(f"[LOGO-STYLE] Inpainting {logo_key}: '{prompt}'")

            output = replicate.run(
                self.model_id,
                input={
                    "image": open(image_path, "rb"),
                    "mask": open(mask_file.name, "rb"),
                    "prompt": prompt,
                    "steps": 50,
                    "guidance": 20,
                    "safety_tolerance": 5,
                    "output_format": "png",
                },
            )

            # Download result
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()

            # Write to temp file first, then rename (atomic)
            tmp_out = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=Path(image_path).parent)
            tmp_out.write(response.content)
            tmp_out.flush()
            os.fsync(tmp_out.fileno())
            tmp_out.close()

            # Convert to match original format
            out_path = Path(image_path)
            result_img = Image.open(tmp_out.name)
            if out_path.suffix.lower() in (".jpg", ".jpeg"):
                result_img.convert("RGB").save(str(out_path), quality=95)
            else:
                result_img.save(str(out_path))

            os.unlink(tmp_out.name)
            print(f"[LOGO-STYLE] Success: {logo_key}")
            return True

        except Exception as e:
            print(f"[LOGO-STYLE] Failed for {logo_key}: {e}")
            return False
        finally:
            if mask_file:
                try:
                    os.unlink(mask_file.name)
                except OSError:
                    pass

    def stylize_logos(
        self,
        image_path: str,
        placements: list[dict],
        logo_styles: dict[str, str],
        image_size: tuple,
    ) -> list[str]:
        """
        Stylize all logos that have style instructions.
        Returns list of logo keys that were successfully stylized.
        """
        if not self.available:
            print("[LOGO-STYLE] Replicate API token not set, skipping stylization")
            return []

        stylized = []
        from .logo_compositor import LOGO_REGISTRY

        for placement in placements:
            key = placement["key"]
            if key not in logo_styles:
                continue

            style = logo_styles[key]
            label = LOGO_REGISTRY.get(key, {}).get("label", key)

            # Build inpainting prompt — describe the icon shape, suppress text hard
            icon_desc = LOGO_ICON_DESCRIPTIONS.get(key, f"{label} logo icon")
            prompt = f"{icon_desc} {style}, icon symbol only, absolutely no text, no words, no letters, no writing, no typography, photorealistic, high quality, detailed, cinematic lighting"

            mask = self.generate_mask(image_size, placement, padding=30)
            success = self.stylize_logo(image_path, mask, prompt, key)
            if success:
                stylized.append(key)

        return stylized
