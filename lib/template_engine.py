"""
Template Engine - Composite YouTube thumbnail templates.

Creates proven thumbnail layouts like "7 Levels", "Pyramid Ranking",
"Grid Collection", and "VS Split" by compositing multiple AI-generated
images into a single structured layout.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math
import os


# Template definitions
TEMPLATES = {
    "levels": {
        "name": "X Levels of Y",
        "description": "Horizontal strip showing levels of increasing intensity/complexity",
        "default_slots": 7,
        "min_slots": 3,
        "max_slots": 10,
        "example": "7 Levels of AI, 5 Levels of Cooking, etc.",
        "claude_instruction": (
            "Generate {slots} levels for '{topic}', from Level 1 (simplest/most basic/easiest) "
            "to Level {slots} (most extreme/complex/advanced). Each level must be a SINGLE, "
            "visually distinct scene or subject that clearly represents that difficulty/complexity tier. "
            "The visual progression should be obvious — Level 1 should look simple/innocent, "
            "Level {slots} should look intense/extreme/mind-blowing."
        ),
    },
    "pyramid": {
        "name": "Pyramid / Tier Ranking",
        "description": "Triangle divided into tiers from broad base to narrow elite top",
        "default_slots": 5,
        "min_slots": 3,
        "max_slots": 7,
        "example": "Ranking foods, ranking skills, tier lists",
        "claude_instruction": (
            "Generate {slots} tiers for a '{topic}' pyramid ranking. "
            "Tier 1 (bottom, widest) = most common/basic. "
            "Tier {slots} (top, narrowest) = rarest/most elite/best. "
            "Each tier should have ONE clear visual subject. "
            "The progression from common to elite should be visually obvious."
        ),
    },
    "grid": {
        "name": "Collection Grid",
        "description": "Grid of items showing a complete collection or comparison set",
        "default_slots": 9,
        "min_slots": 4,
        "max_slots": 16,
        "example": "Every type of X, all the items, complete collection",
        "claude_instruction": (
            "Generate {slots} distinct items/subjects for a '{topic}' collection grid. "
            "Each should be visually unique, recognizable at very small size, and have a "
            "distinct dominant color or shape. Think of it like a visual encyclopedia — "
            "each cell should be instantly identifiable."
        ),
    },
    "vs_split": {
        "name": "VS / Comparison",
        "description": "Two halves showing a dramatic comparison or before/after",
        "default_slots": 2,
        "min_slots": 2,
        "max_slots": 2,
        "example": "X vs Y, Before/After, Old vs New",
        "claude_instruction": (
            "Generate 2 dramatically contrasting visuals for a '{topic}' comparison. "
            "Left side and right side should be visually opposite — different colors, "
            "different mood, different energy. The contrast should be extreme and obvious."
        ),
    },
}


def get_template_info():
    """Return template definitions for the UI."""
    return {
        key: {
            "name": t["name"],
            "description": t["description"],
            "default_slots": t["default_slots"],
            "min_slots": t["min_slots"],
            "max_slots": t["max_slots"],
            "example": t["example"],
        }
        for key, t in TEMPLATES.items()
    }


def get_claude_instruction(template_key: str, topic: str, slots: int) -> str:
    """Get the Claude instruction for generating slot concepts."""
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Unknown template: {template_key}")
    return template["claude_instruction"].format(topic=topic, slots=slots)


class TemplateCompositor:
    """Composites multiple images into template layouts using PIL."""

    # Canvas size (standard YouTube thumbnail)
    CANVAS_WIDTH = 1280
    CANVAS_HEIGHT = 720

    def __init__(self):
        self.fonts = self._find_fonts()

    def _find_fonts(self) -> dict:
        """Find available fonts for number/text overlays."""
        fonts = {"bold": None, "regular": None}

        # Check project fonts directory
        project_fonts = Path(__file__).parent.parent / "fonts"
        font_search_paths = [
            project_fonts / "DeGular-Bold.otf",
            project_fonts / "LemonMilk-Bold.otf",
            Path("/System/Library/Fonts/Helvetica.ttc"),
            Path("/System/Library/Fonts/Arial Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]

        for fp in font_search_paths:
            if fp.exists():
                fonts["bold"] = str(fp)
                break

        return fonts

    def composite(
        self,
        template_key: str,
        images: list[str],
        labels: list[str] = None,
        output_path: str = None,
    ) -> str:
        """
        Composite images into a template layout.

        Args:
            template_key: Which template to use
            images: List of image file paths (one per slot)
            labels: Optional text labels for each slot
            output_path: Where to save the result

        Returns:
            Path to the composited image
        """
        if template_key == "levels":
            return self._composite_levels(images, labels, output_path)
        elif template_key == "pyramid":
            return self._composite_pyramid(images, labels, output_path)
        elif template_key == "grid":
            return self._composite_grid(images, labels, output_path)
        elif template_key == "vs_split":
            return self._composite_split(images, labels, output_path)
        else:
            raise ValueError(f"Unknown template: {template_key}")

    def _composite_levels(
        self, images: list[str], labels: list[str], output_path: str
    ) -> str:
        """Create a horizontal strip with numbered panels."""
        n = len(images)
        canvas = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        panel_width = self.CANVAS_WIDTH // n
        gap = 2  # thin black gap between panels

        # Color gradient for level numbers (green -> yellow -> orange -> red)
        level_colors = self._gradient_colors(n)

        for i, img_path in enumerate(images):
            try:
                img = Image.open(img_path)
                # Crop to fill the panel
                img = self._crop_to_fill(img, panel_width - gap, self.CANVAS_HEIGHT)
                x = i * panel_width + (gap // 2)
                canvas.paste(img, (x, 0))

                # Add number overlay
                number = str(i + 1)
                self._draw_number_badge(
                    draw,
                    number,
                    x + panel_width // 2 - gap // 2,
                    self.CANVAS_HEIGHT - 80,
                    level_colors[i],
                    badge_size=60,
                )

                # Add thin vertical divider
                if i > 0:
                    line_x = i * panel_width
                    draw.line(
                        [(line_x, 0), (line_x, self.CANVAS_HEIGHT)],
                        fill=(0, 0, 0),
                        width=gap,
                    )

            except Exception as e:
                print(f"[TEMPLATE] Error loading image {img_path}: {e}")
                # Draw placeholder
                x = i * panel_width
                draw.rectangle(
                    [x, 0, x + panel_width, self.CANVAS_HEIGHT], fill=(30, 30, 30)
                )

        if output_path is None:
            output_path = str(
                Path(images[0]).parent / f"template_levels_{n}.png"
            )

        canvas.save(output_path, quality=95)
        return output_path

    def _composite_pyramid(
        self, images: list[str], labels: list[str], output_path: str
    ) -> str:
        """Create a pyramid/tier layout."""
        n = len(images)
        canvas = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (20, 20, 20))
        draw = ImageDraw.Draw(canvas)

        # Pyramid: each tier is a horizontal band, narrower toward the top
        tier_height = self.CANVAS_HEIGHT // n
        padding = 4

        for i, img_path in enumerate(images):
            # Tier 0 = top (narrowest), tier n-1 = bottom (widest)
            # Reverse: images[0] = bottom (most common), images[-1] = top (elite)
            tier_idx = n - 1 - i  # 0=top, n-1=bottom

            # Calculate width for this tier (narrower at top)
            min_width = self.CANVAS_WIDTH * 0.25
            max_width = self.CANVAS_WIDTH * 0.95
            tier_width = int(
                min_width + (max_width - min_width) * (tier_idx / max(n - 1, 1))
            )
            x_offset = (self.CANVAS_WIDTH - tier_width) // 2
            y_offset = tier_idx * tier_height

            try:
                img = Image.open(img_path)
                img = self._crop_to_fill(
                    img, tier_width - padding * 2, tier_height - padding
                )
                canvas.paste(img, (x_offset + padding, y_offset + padding // 2))

                # Add tier label
                if labels and i < len(labels):
                    label = labels[i]
                else:
                    label = f"Tier {i + 1}"

                font = self._get_font(max(16, tier_height // 3))
                bbox = draw.textbbox((0, 0), label, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                lx = x_offset + (tier_width - tw) // 2
                ly = y_offset + (tier_height - th) // 2
                draw.text(
                    (lx, ly),
                    label,
                    font=font,
                    fill="#FFFFFF",
                    stroke_width=3,
                    stroke_fill="#000000",
                )

            except Exception as e:
                print(f"[TEMPLATE] Error loading image {img_path}: {e}")

        if output_path is None:
            output_path = str(
                Path(images[0]).parent / f"template_pyramid_{n}.png"
            )

        canvas.save(output_path, quality=95)
        return output_path

    def _composite_grid(
        self, images: list[str], labels: list[str], output_path: str
    ) -> str:
        """Create a grid layout of items."""
        n = len(images)
        # Calculate grid dimensions
        cols = math.ceil(math.sqrt(n * 16 / 9))  # bias toward wider grids for 16:9
        rows = math.ceil(n / cols)

        canvas = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (15, 15, 15))
        draw = ImageDraw.Draw(canvas)

        cell_w = self.CANVAS_WIDTH // cols
        cell_h = self.CANVAS_HEIGHT // rows
        gap = 3

        for i, img_path in enumerate(images):
            row = i // cols
            col = i % cols
            x = col * cell_w + gap
            y = row * cell_h + gap

            try:
                img = Image.open(img_path)
                img = self._crop_to_fill(img, cell_w - gap * 2, cell_h - gap * 2)
                canvas.paste(img, (x, y))
            except Exception as e:
                print(f"[TEMPLATE] Error loading image {img_path}: {e}")
                draw.rectangle(
                    [x, y, x + cell_w - gap * 2, y + cell_h - gap * 2],
                    fill=(30, 30, 30),
                )

        if output_path is None:
            output_path = str(
                Path(images[0]).parent / f"template_grid_{n}.png"
            )

        canvas.save(output_path, quality=95)
        return output_path

    def _composite_split(
        self, images: list[str], labels: list[str], output_path: str
    ) -> str:
        """Create a VS / split comparison layout."""
        canvas = Image.new("RGB", (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        half_w = self.CANVAS_WIDTH // 2
        divider_w = 4

        for i, img_path in enumerate(images[:2]):
            try:
                img = Image.open(img_path)
                img = self._crop_to_fill(
                    img, half_w - divider_w, self.CANVAS_HEIGHT
                )
                x = i * half_w + (divider_w // 2 if i == 0 else divider_w // 2)
                canvas.paste(img, (x, 0))
            except Exception as e:
                print(f"[TEMPLATE] Error loading image {img_path}: {e}")

        # Draw diagonal divider
        draw.line(
            [
                (half_w + 20, 0),
                (half_w - 20, self.CANVAS_HEIGHT),
            ],
            fill=(255, 255, 255),
            width=divider_w,
        )

        # Draw VS badge in center
        vs_font = self._get_font(48)
        draw.text(
            (half_w - 25, self.CANVAS_HEIGHT // 2 - 30),
            "VS",
            font=vs_font,
            fill="#FFFFFF",
            stroke_width=4,
            stroke_fill="#000000",
        )

        # Add labels if provided
        if labels and len(labels) >= 2:
            label_font = self._get_font(28)
            # Left label
            draw.text(
                (20, self.CANVAS_HEIGHT - 60),
                labels[0],
                font=label_font,
                fill="#FFFFFF",
                stroke_width=3,
                stroke_fill="#000000",
            )
            # Right label
            bbox = draw.textbbox((0, 0), labels[1], font=label_font)
            rw = bbox[2] - bbox[0]
            draw.text(
                (self.CANVAS_WIDTH - rw - 20, self.CANVAS_HEIGHT - 60),
                labels[1],
                font=label_font,
                fill="#FFFFFF",
                stroke_width=3,
                stroke_fill="#000000",
            )

        if output_path is None:
            output_path = str(
                Path(images[0]).parent / f"template_vs.png"
            )

        canvas.save(output_path, quality=95)
        return output_path

    # --- Helper methods ---

    def _crop_to_fill(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Crop and resize image to exactly fill target dimensions (center crop)."""
        img_ratio = img.width / img.height
        target_ratio = target_w / target_h

        if img_ratio > target_ratio:
            # Image is wider — crop sides
            new_h = img.height
            new_w = int(new_h * target_ratio)
            left = (img.width - new_w) // 2
            img = img.crop((left, 0, left + new_w, new_h))
        else:
            # Image is taller — crop top/bottom
            new_w = img.width
            new_h = int(new_w / target_ratio)
            top = (img.height - new_h) // 2
            img = img.crop((0, top, new_w, top + new_h))

        return img.resize((target_w, target_h), Image.LANCZOS)

    def _gradient_colors(self, n: int) -> list[str]:
        """Generate a green-to-red gradient for level numbers."""
        colors = []
        for i in range(n):
            ratio = i / max(n - 1, 1)
            if ratio < 0.5:
                # Green to yellow
                r = int(255 * (ratio * 2))
                g = 220
            else:
                # Yellow to red
                r = 255
                g = int(220 * (1 - (ratio - 0.5) * 2))
            colors.append(f"#{r:02x}{g:02x}00")
        return colors

    def _draw_number_badge(
        self,
        draw: ImageDraw.Draw,
        text: str,
        cx: int,
        cy: int,
        color: str,
        badge_size: int = 60,
    ):
        """Draw a numbered circle badge."""
        r = badge_size // 2
        # Background circle
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=color,
            outline="#000000",
            width=3,
        )
        # Number text
        font = self._get_font(badge_size - 16)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (cx - tw // 2, cy - th // 2 - 2),
            text,
            font=font,
            fill="#FFFFFF",
            stroke_width=2,
            stroke_fill="#000000",
        )

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get a font at the specified size."""
        font_path = self.fonts.get("bold")
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()
