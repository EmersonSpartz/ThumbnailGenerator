"""
Auto-detect and composite logos onto generated thumbnails.

Usage:
    compositor = LogoCompositor()
    result_path = compositor.auto_composite(
        image_path="/path/to/thumbnail.jpg",
        text="OpenAI vs Claude battle for control",
    )

The compositor scans text (titles, creative direction, prompts) for mentions
of known logos/icons and composites them onto the image automatically.
"""

import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

# Logo registry: keyword patterns -> logo filename
# Order matters: first match wins for position assignment
LOGO_REGISTRY = {
    "openai": {
        "file": "openai.png",
        "patterns": [r"\bopenai\b", r"\bgpt[-\s]?4\b", r"\bchatgpt\b", r"\bo1\b", r"\bgpt\b"],
        "label": "OpenAI",
    },
    "claude": {
        "file": "claude.png",
        "patterns": [r"\bclaude\b", r"\banthropic\b"],
        "label": "Claude",
    },
    "gemini": {
        "file": "gemini.png",
        "patterns": [r"\bgemini\b", r"\bgoogle\s*ai\b", r"\bbard\b"],
        "label": "Gemini",
    },
    "meta": {
        "file": "meta.png",
        "patterns": [r"\bmeta\s*ai\b", r"\bllama\b", r"\bmeta\b"],
        "label": "Meta",
    },
    "xai": {
        "file": "xai.png",
        "patterns": [r"\bxai\b", r"\bgrok\b", r"\belon\b"],
        "label": "xAI",
    },
    "mistral": {
        "file": "mistral.png",
        "patterns": [r"\bmistral\b"],
        "label": "Mistral",
    },
    "deepseek": {
        "file": "deepseek.png",
        "patterns": [r"\bdeepseek\b", r"\bdeep\s*seek\b"],
        "label": "DeepSeek",
    },
    "perplexity": {
        "file": "perplexity.png",
        "patterns": [r"\bperplexity\b", r"\bpplx\b"],
        "label": "Perplexity",
    },
    "apple": {
        "file": "apple.png",
        "patterns": [r"\bapple\s*intelligence\b", r"\bapple\s*ai\b", r"\bapple\b", r"\bsiri\b"],
        "label": "Apple",
    },
    "microsoft": {
        "file": "microsoft.png",
        "patterns": [r"\bmicrosoft\b", r"\bcopilot\b", r"\bbing\s*ai\b"],
        "label": "Microsoft",
    },
    "aws": {
        "file": "aws.png",
        "patterns": [r"\baws\b", r"\bamazon\b", r"\bbedrock\b"],
        "label": "AWS",
    },
    "nvidia": {
        "file": "nvidia.png",
        "patterns": [r"\bnvidia\b", r"\bgeforce\b", r"\bcuda\b"],
        "label": "NVIDIA",
    },
    "samsung": {
        "file": "samsung.png",
        "patterns": [r"\bsamsung\b", r"\bgalaxy\s*ai\b"],
        "label": "Samsung",
    },
    "cohere": {
        "file": "cohere.png",
        "patterns": [r"\bcohere\b", r"\bcommand\s*r\b"],
        "label": "Cohere",
    },
    "arrow": {
        "file": "arrow.png",
        "patterns": [r"\barrow\b"],
        "label": "Arrow",
    },
    "vs": {
        "file": "vs.png",
        "patterns": [r"\bvs\.?\b", r"\bversus\b", r"\bvs\b"],
        "label": "VS",
    },
    "question": {
        "file": "question.png",
        "patterns": [r"\bmystery\b", r"\bquestion\s*mark\b", r"\bunknown\b"],
        "label": "?",
    },
}

# Layout presets for common arrangements
LAYOUTS = {
    "vs": {
        # Two logos on opposite sides with VS in center
        "positions": [
            {"x_ratio": 0.12, "y_ratio": 0.35, "size_ratio": 0.28},  # Left logo
            {"x_ratio": 0.88, "y_ratio": 0.35, "size_ratio": 0.28},  # Right logo
        ],
        "vs_badge": {"x_ratio": 0.50, "y_ratio": 0.50, "size_ratio": 0.18},
    },
    "single": {
        # One logo, prominent placement
        "positions": [
            {"x_ratio": 0.50, "y_ratio": 0.40, "size_ratio": 0.30},
        ],
    },
    "triple": {
        # Three logos spread across
        "positions": [
            {"x_ratio": 0.18, "y_ratio": 0.40, "size_ratio": 0.22},
            {"x_ratio": 0.50, "y_ratio": 0.40, "size_ratio": 0.22},
            {"x_ratio": 0.82, "y_ratio": 0.40, "size_ratio": 0.22},
        ],
    },
    "multi": {
        # 4+ logos in a row
        "positions": [],  # dynamically calculated
    },
}


class LogoCompositor:
    def __init__(self, logo_dir: str = None):
        if logo_dir:
            self.logo_dir = Path(logo_dir)
        else:
            self.logo_dir = Path(__file__).parent.parent / "logos"

    def detect_logos(self, text: str) -> list[str]:
        """
        Scan text for mentions of known logos/icons.
        Returns list of logo keys in order of appearance.
        """
        if not text:
            return []

        text_lower = text.lower()
        found = []

        for key, info in LOGO_REGISTRY.items():
            for pattern in info["patterns"]:
                if re.search(pattern, text_lower):
                    if key not in found:
                        found.append(key)
                    break

        return found

    def detect_is_vs(self, text: str) -> bool:
        """Check if this is a versus/comparison context."""
        if not text:
            return False
        text_lower = text.lower()
        return bool(re.search(r"\bvs\.?\b|\bversus\b|\bvs\b|\bagainst\b|\bcompete\b|\bfight\b|\bbattle\b|\brival\b", text_lower))

    def choose_layout(self, logo_keys: list[str], text: str) -> dict:
        """Choose the best layout based on detected logos and context."""
        is_vs = self.detect_is_vs(text)

        # Filter out 'vs' from logo list (it's placed separately)
        content_logos = [k for k in logo_keys if k != "vs"]

        if len(content_logos) == 2 and is_vs:
            return "vs", content_logos
        elif len(content_logos) == 1:
            return "single", content_logos
        elif len(content_logos) == 3:
            return "triple", content_logos
        elif len(content_logos) >= 2 and is_vs:
            # VS with first two logos
            return "vs", content_logos[:2]
        elif len(content_logos) >= 2:
            return "triple", content_logos[:3]
        else:
            return "single", content_logos

    def load_logo(self, key: str) -> Image.Image:
        """Load a logo PNG with transparency."""
        info = LOGO_REGISTRY.get(key)
        if not info:
            return None

        path = self.logo_dir / info["file"]
        if not path.exists():
            return None

        img = Image.open(path).convert("RGBA")
        return img

    def add_drop_shadow(self, logo: Image.Image, offset: int = 6, blur_radius: int = 12, opacity: int = 180) -> Image.Image:
        """Add a drop shadow + white glow behind the logo for visibility on any background."""
        pad = blur_radius * 3
        shadow_size = (logo.width + pad * 2, logo.height + pad * 2)
        result = Image.new("RGBA", shadow_size, (0, 0, 0, 0))

        alpha = logo.split()[3]  # Alpha channel

        # Layer 1: White glow (ensures visibility on dark backgrounds)
        glow = Image.new("RGBA", logo.size, (255, 255, 255, 140))
        glow.putalpha(alpha)
        result.paste(glow, (pad, pad))
        result = result.filter(ImageFilter.GaussianBlur(blur_radius + 4))

        # Layer 2: Dark shadow (ensures visibility on light backgrounds)
        shadow_layer = Image.new("RGBA", shadow_size, (0, 0, 0, 0))
        shadow_img = Image.new("RGBA", logo.size, (0, 0, 0, opacity))
        shadow_img.putalpha(alpha)
        shadow_layer.paste(shadow_img, (pad + offset, pad + offset))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_radius))

        # Combine: glow first, then shadow, then logo
        result = Image.alpha_composite(result, shadow_layer)
        logo_layer = Image.new("RGBA", shadow_size, (0, 0, 0, 0))
        logo_layer.paste(logo, (pad, pad), logo)
        result = Image.alpha_composite(result, logo_layer)

        return result

    def detect_logo_styles(self, text: str) -> dict[str, str]:
        """
        Extract per-logo style instructions from creative direction text.
        E.g., "OpenAI logo dripping blood" -> {"openai": "dripping blood"}
        Returns empty dict if no style instructions found (plain compositing).
        """
        if not text:
            return {}

        text_lower = text.lower()
        styles = {}

        for key, info in LOGO_REGISTRY.items():
            if key in ("vs", "arrow", "question"):
                continue  # utility icons, not stylizable

            label = info["label"].lower()
            # Match patterns like "OpenAI logo dripping blood" or "Claude on fire"
            patterns = [
                rf"\b{re.escape(label)}\s+logo\s+([\w\s'\"]+?)(?:,|\band\b|\bvs\b|$)",
                rf"\b{re.escape(label)}\s+(on fire|glowing|melting|dripping[\w\s]*|exploding|bloody|evil|dark|red|blue|green|gold|golden|neon|chrome|metallic|holding[\w\s]*|with[\w\s]*|wrapped[\w\s]*|covered[\w\s]*)(?:,|\band\b|\bvs\b|$)",
            ]
            for pat in patterns:
                m = re.search(pat, text_lower)
                if m:
                    style = m.group(1).strip()
                    if style and len(style) > 2:  # skip trivial matches
                        styles[key] = style
                    break

        return styles

    def composite_logos(
        self,
        image_path: str,
        logo_keys: list[str],
        text: str = "",
        output_path: str = None,
    ) -> tuple[str, list[dict]]:
        """
        Composite detected logos onto an image.

        Args:
            image_path: Path to the source image
            logo_keys: List of logo keys to place
            text: Original text (for layout detection)
            output_path: Where to save (defaults to overwrite source)

        Returns:
            Tuple of (path to composited image, list of placement dicts)
        """
        if not logo_keys:
            return image_path, []

        # Load base image
        base = Image.open(image_path).convert("RGBA")
        width, height = base.size

        # Choose layout
        layout_name, content_logos = self.choose_layout(logo_keys, text)

        if not content_logos:
            return image_path, []

        placements = []

        # Get positions for this layout
        if layout_name == "vs":
            positions = LAYOUTS["vs"]["positions"][:len(content_logos)]
        elif layout_name == "single":
            positions = LAYOUTS["single"]["positions"]
        elif layout_name == "triple":
            positions = LAYOUTS["triple"]["positions"][:len(content_logos)]
        else:
            # Dynamic: spread evenly
            n = len(content_logos)
            positions = []
            for i in range(n):
                positions.append({
                    "x_ratio": (i + 1) / (n + 1),
                    "y_ratio": 0.40,
                    "size_ratio": min(0.22, 0.60 / n),
                })

        # Composite each logo
        for i, key in enumerate(content_logos):
            if i >= len(positions):
                break

            logo = self.load_logo(key)
            if not logo:
                continue

            pos = positions[i]
            target_size = int(height * pos["size_ratio"])

            # Resize logo maintaining aspect ratio
            logo_ratio = logo.width / logo.height
            if logo_ratio > 1:
                new_w = target_size
                new_h = int(target_size / logo_ratio)
            else:
                new_h = target_size
                new_w = int(target_size * logo_ratio)

            logo = logo.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Add drop shadow
            logo_with_shadow = self.add_drop_shadow(logo)

            # Calculate position (centered on the ratio point)
            x = int(width * pos["x_ratio"] - logo_with_shadow.width // 2)
            y = int(height * pos["y_ratio"] - logo_with_shadow.height // 2)

            # Clamp to image bounds
            x = max(0, min(x, width - logo_with_shadow.width))
            y = max(0, min(y, height - logo_with_shadow.height))

            base.paste(logo_with_shadow, (x, y), logo_with_shadow)

            # Track placement for potential stylization
            placements.append({
                "key": key,
                "x": x,
                "y": y,
                "width": logo_with_shadow.width,
                "height": logo_with_shadow.height,
            })

        # Add VS badge if it's a versus layout
        if layout_name == "vs" and len(content_logos) >= 2:
            vs_logo = self.load_logo("vs")
            if vs_logo:
                vs_pos = LAYOUTS["vs"]["vs_badge"]
                vs_size = int(height * vs_pos["size_ratio"])
                vs_logo = vs_logo.resize((vs_size, vs_size), Image.Resampling.LANCZOS)
                vs_with_shadow = self.add_drop_shadow(vs_logo, offset=4, blur_radius=8)

                vx = int(width * vs_pos["x_ratio"] - vs_with_shadow.width // 2)
                vy = int(height * vs_pos["y_ratio"] - vs_with_shadow.height // 2)
                base.paste(vs_with_shadow, (vx, vy), vs_with_shadow)

        # Save
        if output_path is None:
            output_path = image_path

        # Convert to RGB for JPEG output
        out_path = Path(output_path)
        if out_path.suffix.lower() in (".jpg", ".jpeg"):
            rgb = Image.new("RGB", base.size, (0, 0, 0))
            rgb.paste(base, mask=base.split()[3] if base.mode == "RGBA" else None)
            rgb.save(str(out_path), quality=95)
        else:
            base.save(str(out_path))

        return str(out_path), placements

    def auto_composite(
        self,
        image_path: str,
        title: str = "",
        creative_direction: str = "",
        concept_name: str = "",
        output_path: str = None,
    ) -> tuple[str, list[str], list[dict]]:
        """
        Full auto pipeline: detect logos from text, composite onto image.

        Args:
            image_path: Path to the generated thumbnail
            title: Video title
            creative_direction: User's creative direction text
            concept_name: The concept name from Claude
            output_path: Where to save (defaults to overwrite)

        Returns:
            Tuple of (output_path, list of logo keys applied, list of placement dicts)
        """
        # Combine all text for detection
        combined_text = f"{title} {creative_direction} {concept_name}"

        # Detect which logos to place
        logo_keys = self.detect_logos(combined_text)

        if not logo_keys:
            return image_path, [], []

        # Filter to only logos that have files
        available = [k for k in logo_keys if (self.logo_dir / LOGO_REGISTRY[k]["file"]).exists()]

        if not available:
            return image_path, [], []

        result_path, placements = self.composite_logos(
            image_path=image_path,
            logo_keys=available,
            text=combined_text,
            output_path=output_path,
        )

        return result_path, available, placements
