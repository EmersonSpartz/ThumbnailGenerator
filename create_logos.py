#!/usr/bin/env python3
"""Generate placeholder AI company logos as transparent PNGs.
Replace these with official logos for best results."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

LOGO_DIR = Path(__file__).parent / "logos"
LOGO_DIR.mkdir(exist_ok=True)

SIZE = 512  # px, will be scaled down during compositing


def create_circle_logo(filename, bg_color, text, text_color="white", font_size=200):
    """Create a circular logo with text."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw circle
    margin = 10
    draw.ellipse([margin, margin, SIZE - margin, SIZE - margin], fill=bg_color)

    # Draw text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (SIZE - tw) // 2
    y = (SIZE - th) // 2 - bbox[1]
    draw.text((x, y), text, fill=text_color, font=font)

    img.save(LOGO_DIR / filename)
    print(f"  Created {filename}")


def create_openai_logo():
    """OpenAI - black circle with white hexagonal knot."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Black circle
    margin = 10
    draw.ellipse([margin, margin, SIZE - margin, SIZE - margin], fill=(0, 0, 0, 255))

    # Simplified hexagonal knot shape
    cx, cy = SIZE // 2, SIZE // 2
    r = SIZE * 0.30

    # Draw 6 curved lines forming a knot
    line_width = 28
    for i in range(6):
        angle1 = math.radians(60 * i - 30)
        angle2 = math.radians(60 * i + 30)
        x1 = cx + r * math.cos(angle1)
        y1 = cy + r * math.sin(angle1)
        x2 = cx + r * math.cos(angle2)
        y2 = cy + r * math.sin(angle2)

        # Extend lines outward
        angle_out = math.radians(60 * i)
        x_out = cx + r * 1.35 * math.cos(angle_out)
        y_out = cy + r * 1.35 * math.sin(angle_out)

        draw.line([(x1, y1), (x_out, y_out)], fill="white", width=line_width)
        draw.line([(x2, y2), (x_out, y_out)], fill="white", width=line_width)

    img.save(LOGO_DIR / "openai.png")
    print("  Created openai.png")


def create_claude_logo():
    """Claude/Anthropic - orange/terracotta circle with sparkle."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Anthropic tan/orange
    draw.ellipse([10, 10, SIZE - 10, SIZE - 10], fill=(204, 120, 67, 255))

    # Simple sparkle/star shape in center
    cx, cy = SIZE // 2, SIZE // 2

    # 4-pointed star
    points_outer = []
    points_inner = []
    r_out = SIZE * 0.28
    r_in = SIZE * 0.08

    for i in range(8):
        angle = math.radians(45 * i - 90)
        r = r_out if i % 2 == 0 else r_in
        points_outer.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    draw.polygon(points_outer, fill="white")

    img.save(LOGO_DIR / "claude.png")
    print("  Created claude.png")


def create_gemini_logo():
    """Google Gemini - blue gradient star."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Blue circle
    draw.ellipse([10, 10, SIZE - 10, SIZE - 10], fill=(66, 133, 244, 255))

    # White 4-pointed star
    cx, cy = SIZE // 2, SIZE // 2
    r_out = SIZE * 0.32
    r_in = SIZE * 0.06

    points = []
    for i in range(8):
        angle = math.radians(45 * i - 90)
        r = r_out if i % 2 == 0 else r_in
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    draw.polygon(points, fill="white")

    img.save(LOGO_DIR / "gemini.png")
    print("  Created gemini.png")


def create_meta_logo():
    """Meta - blue circle with infinity symbol."""
    create_circle_logo("meta.png", (24, 119, 242), "M", font_size=280)


def create_xai_logo():
    """xAI/Grok - black with X."""
    create_circle_logo("xai.png", (0, 0, 0), "X", font_size=300)


def create_mistral_logo():
    """Mistral - orange with M."""
    create_circle_logo("mistral.png", (245, 130, 32), "M", font_size=280)


def create_arrow():
    """Arrow - transparent PNG arrow pointing right."""
    img = Image.new("RGBA", (SIZE, SIZE // 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Arrow body
    w, h = SIZE, SIZE // 2
    body_top = h * 0.3
    body_bot = h * 0.7
    head_start = w * 0.6

    # Arrow shaft
    draw.rectangle([w * 0.1, body_top, head_start, body_bot], fill=(255, 50, 50, 255))

    # Arrow head (triangle)
    draw.polygon([
        (head_start, h * 0.1),
        (w * 0.9, h * 0.5),
        (head_start, h * 0.9)
    ], fill=(255, 50, 50, 255))

    # White border/outline for visibility
    draw.line([(w * 0.1, body_top), (head_start, body_top), (head_start, h * 0.1),
               (w * 0.9, h * 0.5), (head_start, h * 0.9), (head_start, body_bot),
               (w * 0.1, body_bot), (w * 0.1, body_top)], fill="white", width=8)

    img.save(LOGO_DIR / "arrow.png")
    print("  Created arrow.png")


def create_vs_badge():
    """VS badge for versus comparisons."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Red circle with white border
    draw.ellipse([10, 10, SIZE - 10, SIZE - 10], fill=(220, 38, 38), outline="white", width=12)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 220)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "VS", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - tw) // 2, (SIZE - th) // 2 - bbox[1]), "VS", fill="white", font=font)

    img.save(LOGO_DIR / "vs.png")
    print("  Created vs.png")


def create_question_mark():
    """Question mark for mystery/curiosity thumbnails."""
    create_circle_logo("question.png", (139, 92, 246), "?", font_size=350)


if __name__ == "__main__":
    print("Creating logo library...")
    create_openai_logo()
    create_claude_logo()
    create_gemini_logo()
    create_meta_logo()
    create_xai_logo()
    create_mistral_logo()
    create_arrow()
    create_vs_badge()
    create_question_mark()
    print(f"\nDone! {len(list(LOGO_DIR.glob('*.png')))} logos in {LOGO_DIR}")
    print("\nTip: Replace these placeholders with official logos for best results.")
