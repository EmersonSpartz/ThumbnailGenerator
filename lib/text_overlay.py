"""
Text Overlay System - Add text to thumbnails without Photoshop.

Supports:
- Bold impact text (big words like "SHOCKING")
- Phrases with different styles
- Numbers and stats
- Multiple text positions
- Various fonts and effects
- AI-powered safe zone detection
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os
import base64
import json
import re

# Anthropic for Claude Vision
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class TextOverlay:
    """Add professional text overlays to thumbnail images."""

    # Pre-defined text styles
    STYLES = {
        "impact": {
            "font_size_ratio": 0.15,  # Relative to image height
            "color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width_ratio": 0.008,
            "uppercase": True,
            "font_weight": "bold",
        },
        "subtitle": {
            "font_size_ratio": 0.06,
            "color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width_ratio": 0.004,
            "uppercase": False,
            "font_weight": "regular",
        },
        "number": {
            "font_size_ratio": 0.20,
            "color": "#FFFF00",  # Yellow for attention
            "stroke_color": "#000000",
            "stroke_width_ratio": 0.01,
            "uppercase": True,
            "font_weight": "bold",
        },
        "label": {
            "font_size_ratio": 0.05,
            "color": "#FFFFFF",
            "background_color": "#FF0000",
            "padding": 10,
            "uppercase": True,
            "font_weight": "bold",
        },
    }

    # Text positions
    POSITIONS = {
        "top-left": (0.05, 0.08),
        "top-center": (0.5, 0.08),
        "top-right": (0.95, 0.08),
        "center": (0.5, 0.5),
        "bottom-left": (0.05, 0.88),
        "bottom-center": (0.5, 0.88),
        "bottom-right": (0.95, 0.88),
    }

    def __init__(self):
        # Try to find system fonts
        self.fonts = self._find_fonts()

    def _find_fonts(self) -> dict:
        """Find available fonts, prioritizing Lemon Milk."""
        fonts = {"bold": None, "regular": None, "lemonmilk": None}

        # Get the project fonts directory
        project_dir = Path(__file__).parent.parent
        fonts_dir = project_dir / "fonts"

        # Priority 1: Lemon Milk (preferred for thumbnails)
        lemon_milk_paths = [
            fonts_dir / "LEMONMILK-Bold.otf",
            fonts_dir / "LEMONMILK-Medium.otf",
            fonts_dir / "LEMONMILK-Regular.otf",
        ]
        for font_path in lemon_milk_paths:
            if font_path.exists():
                fonts["lemonmilk"] = str(font_path)
                fonts["bold"] = str(font_path)  # Use as default bold
                break

        # Priority 2: System bold fonts (fallback)
        if fonts["bold"] is None:
            mac_bold_fonts = [
                "/System/Library/Fonts/Supplemental/Impact.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                "/Library/Fonts/Arial.ttf",
            ]
            for font_path in mac_bold_fonts:
                if os.path.exists(font_path):
                    fonts["bold"] = font_path
                    break

        # Regular fonts
        regular_fonts = [
            fonts_dir / "LEMONMILK-Regular.otf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
        ]
        for font_path in regular_fonts:
            path_str = str(font_path) if isinstance(font_path, Path) else font_path
            if os.path.exists(path_str):
                fonts["regular"] = path_str
                break

        return fonts

    def add_text(
        self,
        image_path: str,
        text: str,
        position: str = "bottom-center",
        style: str = "impact",
        custom_color: str = None,
        output_path: str = None,
    ) -> str:
        """
        Add text to an image.

        Args:
            image_path: Path to the source image
            text: The text to add
            position: Where to place text (top-left, center, bottom-right, etc.)
            style: Text style (impact, subtitle, number, label)
            custom_color: Override the style's default color
            output_path: Where to save (defaults to same location with _text suffix)

        Returns:
            Path to the new image with text
        """
        # Load image
        img = Image.open(image_path)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        draw = ImageDraw.Draw(img)
        width, height = img.size

        # Get style settings
        style_config = self.STYLES.get(style, self.STYLES["impact"])

        # Calculate font size
        font_size = int(height * style_config["font_size_ratio"])

        # Load font
        font_weight = style_config.get("font_weight", "bold")
        font_path = self.fonts.get(font_weight) or self.fonts.get("bold")

        try:
            if font_path:
                font = ImageFont.truetype(font_path, font_size)
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        # Process text
        if style_config.get("uppercase", False):
            text = text.upper()

        # Get text size
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Calculate position
        pos_ratios = self.POSITIONS.get(position, (0.5, 0.5))
        x = int(width * pos_ratios[0])
        y = int(height * pos_ratios[1])

        # Adjust for text alignment
        if "center" in position or position == "center":
            x -= text_width // 2
        elif "right" in position:
            x -= text_width
        y -= text_height // 2

        # Get colors
        fill_color = custom_color or style_config["color"]
        stroke_color = style_config.get("stroke_color", "#000000")
        stroke_width = int(height * style_config.get("stroke_width_ratio", 0.005))

        # Draw background box if style has it
        if "background_color" in style_config:
            padding = style_config.get("padding", 10)
            bg_box = [
                x - padding,
                y - padding,
                x + text_width + padding,
                y + text_height + padding
            ]
            draw.rectangle(bg_box, fill=style_config["background_color"])

        # Draw text with stroke (outline) for readability
        if stroke_width > 0:
            draw.text(
                (x, y),
                text,
                font=font,
                fill=fill_color,
                stroke_width=stroke_width,
                stroke_fill=stroke_color
            )
        else:
            draw.text((x, y), text, font=font, fill=fill_color)

        # Save
        if output_path is None:
            path = Path(image_path)
            output_path = str(path.parent / f"{path.stem}_text{path.suffix}")

        # Convert back to RGB for saving as JPEG/PNG
        if output_path.lower().endswith('.jpg') or output_path.lower().endswith('.jpeg'):
            img = img.convert('RGB')

        img.save(output_path, quality=95)
        return output_path

    def add_multiple_texts(
        self,
        image_path: str,
        texts: list[dict],
        output_path: str = None,
    ) -> str:
        """
        Add multiple text elements to an image.

        Args:
            image_path: Path to the source image
            texts: List of text configs, each with:
                   {"text": "...", "position": "...", "style": "...", "color": "..."}
            output_path: Where to save

        Returns:
            Path to the new image
        """
        # Process each text one by one
        current_path = image_path

        for i, text_config in enumerate(texts):
            is_last = i == len(texts) - 1
            out = output_path if is_last else None

            current_path = self.add_text(
                image_path=current_path,
                text=text_config.get("text", ""),
                position=text_config.get("position", "center"),
                style=text_config.get("style", "impact"),
                custom_color=text_config.get("color"),
                output_path=out,
            )

        return current_path

    def get_available_styles(self) -> dict:
        """Return available text styles for the UI."""
        return {
            name: {
                "description": self._style_description(name),
                "preview_color": config.get("color", "#FFFFFF")
            }
            for name, config in self.STYLES.items()
        }

    def _style_description(self, style_name: str) -> str:
        descriptions = {
            "impact": "Big bold text - great for 1-3 word hooks",
            "subtitle": "Smaller text for phrases",
            "number": "Yellow numbers that pop - for stats",
            "label": "Red background label - for categories",
        }
        return descriptions.get(style_name, style_name)

    def analyze_safe_zones(self, image_path: str) -> dict:
        """
        Use Claude Vision to analyze the image and find safe zones for text placement.

        Returns:
            Dict with recommended positions and reasoning
        """
        if not ANTHROPIC_AVAILABLE:
            # Fallback: suggest common safe positions
            return {
                "recommended_positions": ["top-left", "bottom-right"],
                "reasoning": "Claude Vision not available, using default positions",
                "focal_point": "center",
                "safe_zones": ["top-left", "top-right", "bottom-left", "bottom-right"]
            }

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "recommended_positions": ["top-left", "bottom-right"],
                "reasoning": "No API key, using default positions",
                "focal_point": "center",
                "safe_zones": ["top-left", "top-right", "bottom-left", "bottom-right"]
            }

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            # Determine media type
            ext = Path(image_path).suffix.lower()
            media_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }.get(ext, "image/jpeg")

            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            }
                        },
                        {
                            "type": "text",
                            "text": """Analyze this YouTube thumbnail image for text placement.

I need to overlay text on this image. Tell me:
1. Where is the focal point / main subject? (e.g., "center", "left-center", "right-third")
2. Which areas are SAFE for text (won't cover important content)?
3. Rank the best positions for text from this list: top-left, top-center, top-right, bottom-left, bottom-center, bottom-right

Return ONLY valid JSON:
{
    "focal_point": "description of where the main subject is",
    "safe_zones": ["position1", "position2", ...],
    "recommended_positions": ["best", "second-best"],
    "reasoning": "brief explanation"
}"""
                        }
                    ]
                }]
            )

            # Parse response
            text = response.content[0].text
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "recommended_positions": ["top-left", "bottom-right"],
                    "reasoning": "Could not parse Claude response",
                    "focal_point": "unknown",
                    "safe_zones": ["top-left", "bottom-right"]
                }

        except Exception as e:
            return {
                "recommended_positions": ["top-left", "bottom-right"],
                "reasoning": f"Error analyzing image: {str(e)[:100]}",
                "focal_point": "unknown",
                "safe_zones": ["top-left", "top-right", "bottom-left", "bottom-right"]
            }

    def generate_text_variations(
        self,
        image_path: str,
        text_copies: list[str],
        position: str = None,
        style: str = "impact",
        output_dir: str = None,
    ) -> list[dict]:
        """
        Generate multiple versions of an image with different text overlays.

        Args:
            image_path: Path to the source image
            text_copies: List of text strings to overlay (one per output image)
            position: Where to place text (if None, will auto-detect)
            style: Text style to use
            output_dir: Directory to save outputs (defaults to same as source)

        Returns:
            List of dicts with {text, file_path, position}
        """
        results = []

        # Auto-detect best position if not specified
        if position is None:
            analysis = self.analyze_safe_zones(image_path)
            recommended = analysis.get("recommended_positions", ["top-left"])
            position = recommended[0] if recommended else "top-left"

        # Set up output directory
        if output_dir is None:
            output_dir = Path(image_path).parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        # Generate each variation
        source_stem = Path(image_path).stem

        for i, text in enumerate(text_copies):
            if not text.strip():
                continue

            # Create unique output filename
            safe_text = re.sub(r'[^a-zA-Z0-9]', '_', text[:20]).strip('_')
            output_filename = f"{source_stem}_text_{i+1}_{safe_text}.png"
            output_path = str(output_dir / output_filename)

            try:
                saved_path = self.add_text(
                    image_path=image_path,
                    text=text,
                    position=position,
                    style=style,
                    output_path=output_path
                )

                results.append({
                    "text": text,
                    "file_path": saved_path,
                    "position": position,
                    "style": style,
                    "success": True
                })
            except Exception as e:
                results.append({
                    "text": text,
                    "file_path": None,
                    "position": position,
                    "style": style,
                    "success": False,
                    "error": str(e)
                })

        return results
