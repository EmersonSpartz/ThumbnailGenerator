"""
Species Post-Processor — applies the Species channel's signature visual style
to AI-generated thumbnail images.

Effects (matching the Screenshake style guide):
1. Bayer dithering on background
2. Red accent glow
3. CRT scan lines
4. Chromatic aberration
5. Film grain/noise

All effects have adjustable intensity. Can be toggled on/off individually.
"""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
from pathlib import Path
from typing import Optional


# Species brand colors
SHOGGOTH_RED = (226, 0, 32)      # #E20020
GLITCH_CYAN = (34, 226, 255)     # #22E2FF
GLITCH_MAGENTA = (247, 50, 239)  # #F732EF


def _generate_bayer_matrix(n: int) -> np.ndarray:
    """Generate an n×n Bayer dithering threshold matrix (n must be power of 2)."""
    if n == 2:
        return np.array([[0, 2], [3, 1]], dtype=np.float32)
    smaller = _generate_bayer_matrix(n // 2)
    return np.block([
        [4 * smaller + 0, 4 * smaller + 2],
        [4 * smaller + 3, 4 * smaller + 1]
    ])


def apply_bayer_dither(img: Image.Image, strength: float = 0.3, levels: int = 8) -> Image.Image:
    """
    Apply Bayer algorithmic dithering to an image.

    This creates the distinctive pixelated gradient texture seen in Species thumbnails.
    Only applies heavily to dark areas (backgrounds), preserving bright subjects.

    Uses a 4x4 Bayer matrix scaled up 2x for visible dot pattern at thumbnail resolution.
    """
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Generate 4x4 Bayer matrix — larger dots, more visible at thumbnail size
    bayer = _generate_bayer_matrix(4)
    bayer = bayer / bayer.max()  # Normalize to 0-1

    # Scale up each cell by 2x to make individual dots visible (effective 8x8 grid)
    bayer_scaled = np.repeat(np.repeat(bayer, 2, axis=0), 2, axis=1)
    bayer_tiled = np.tile(bayer_scaled, (h // 8 + 1, w // 8 + 1))[:h, :w]

    # Calculate luminance to determine how much dithering to apply
    # Real Species thumbnails dither dark AND mid-tone areas heavily
    # Only the brightest highlights are preserved
    luminance = np.mean(arr, axis=2) / 255.0
    # Dithering mask: full strength on dark, tapers off only for very bright areas
    dither_mask = np.clip(1.0 - luminance * 0.8, 0.05, 1) * strength

    # Quantize to fewer levels with Bayer threshold
    for c in range(3):
        channel = arr[:, :, c] / 255.0
        # Add Bayer threshold offset before quantization — stronger multiplier
        # for more visible dot pattern matching real Species channel
        dithered = channel + (bayer_tiled - 0.5) * dither_mask * 0.9
        # Quantize to discrete levels
        quantized = np.round(dithered * (levels - 1)) / (levels - 1)
        # Blend between original and dithered based on mask
        arr[:, :, c] = (channel * (1 - dither_mask) + quantized * dither_mask) * 255

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_red_glow(img: Image.Image, strength: float = 0.25, position: str = "bottom") -> Image.Image:
    """
    Add a red (#E20020) glow, typically at the bottom of the thumbnail.
    This is the signature Species look — ominous red emergency lighting.

    Smart application: only adds red glow to dark areas of the image.
    Bright or non-dark-red areas are left alone so the glow doesn't clash
    with existing color palettes (e.g. gold, blue, green images).
    """
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Create gradient mask based on position
    if position == "bottom":
        gradient = np.linspace(0, 1, h).reshape(-1, 1)
        gradient = gradient ** 1.5  # Concentrate at bottom
    elif position == "top":
        gradient = np.linspace(1, 0, h).reshape(-1, 1)
        gradient = gradient ** 1.5
    elif position == "center":
        y = np.linspace(-1, 1, h).reshape(-1, 1)
        x = np.linspace(-1, 1, w).reshape(1, -1)
        gradient = np.exp(-(x**2 + y**2) * 1.5)
    else:
        gradient = np.linspace(0, 1, h).reshape(-1, 1)

    # Broadcast to full image size
    if gradient.ndim == 1 or (gradient.ndim == 2 and gradient.shape[1] == 1):
        gradient = np.broadcast_to(gradient, (h, w))

    # Smart mask: only apply red glow to DARK areas of the image
    # This prevents clashing with bright subjects or non-red color palettes
    luminance = np.mean(arr, axis=2) / 255.0  # 0=black, 1=white
    dark_mask = np.clip(1.0 - luminance * 2.0, 0, 1)  # Strong on dark, zero on bright

    # Combine position gradient with darkness mask
    combined_mask = gradient * dark_mask

    # Apply red glow — additive blending, only where it's dark
    red_layer = np.zeros_like(arr)
    red_layer[:, :, 0] = SHOGGOTH_RED[0] * combined_mask * strength
    red_layer[:, :, 1] = SHOGGOTH_RED[1] * combined_mask * strength
    red_layer[:, :, 2] = SHOGGOTH_RED[2] * combined_mask * strength

    result = arr + red_layer
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def apply_crt_scanlines(img: Image.Image, strength: float = 0.15, line_width: int = 2) -> Image.Image:
    """
    Add CRT scan line effect — semi-transparent horizontal lines.
    Uses a soft sine-wave pattern instead of hard on/off for a more
    authentic CRT look. Slight green tint on bright lines for realism.
    """
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Smooth sine-wave scanline pattern (more authentic than hard lines)
    y = np.arange(h, dtype=np.float32)
    # Period of line_width*2 pixels, smoothly varying
    scanline_wave = 0.5 + 0.5 * np.sin(y * np.pi / line_width)
    # Map to darkening factor: 1.0 (no change) to (1-strength) (darkened)
    scanlines = 1.0 - strength * (1.0 - scanline_wave)
    scanlines = scanlines.reshape(-1, 1)
    scanlines = np.broadcast_to(scanlines, (h, w))

    for c in range(3):
        arr[:, :, c] *= scanlines

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_chromatic_aberration(img: Image.Image, strength: int = 3) -> Image.Image:
    """
    Apply chromatic aberration — offset RGB channels slightly.
    Creates the glitchy color fringing effect on edges, especially toward
    the periphery of the image (like real lens distortion).
    """
    arr = np.array(img)
    h, w = arr.shape[:2]
    result = np.zeros_like(arr)

    # Create radial strength map — stronger at edges, zero at center
    y_coords = np.linspace(-1, 1, h).reshape(-1, 1)
    x_coords = np.linspace(-1, 1, w).reshape(1, -1)
    radial = np.sqrt(x_coords**2 + y_coords**2)
    radial = np.clip(radial, 0, 1)

    # Per-pixel offset in x direction, scaled by distance from center
    offset_map = (radial * strength).astype(np.int32)

    # Red channel shifts left, blue shifts right, green stays
    for y in range(h):
        for x in range(w):
            off = offset_map[y, x]
            # Red - shift left
            rx = max(0, x - off)
            result[y, x, 0] = arr[y, rx, 0]
            # Green - no shift
            result[y, x, 1] = arr[y, x, 1]
            # Blue - shift right
            bx = min(w - 1, x + off)
            result[y, x, 2] = arr[y, bx, 2]

    return Image.fromarray(result)


def apply_chromatic_aberration_fast(img: Image.Image, strength: int = 3) -> Image.Image:
    """
    Fast vectorized radial chromatic aberration.
    Stronger at edges (like real lens distortion), minimal at center.
    Uses numpy fancy indexing — no Python loops.
    """
    arr = np.array(img)
    h, w = arr.shape[:2]
    result = arr.copy()

    # Build coordinate grids
    y_idx = np.arange(h).reshape(-1, 1)
    x_idx = np.arange(w).reshape(1, -1)

    # Radial distance from center (0 at center, ~1 at corners)
    cy, cx = h / 2, w / 2
    radial = np.sqrt(((x_idx - cx) / cx) ** 2 + ((y_idx - cy) / cy) ** 2)
    radial = np.clip(radial, 0, 1.4)  # Allow >1 at corners

    # Per-pixel horizontal offset, scaled by radial distance
    offset = (radial * strength).astype(np.int32)

    # Red channel shifts LEFT by offset (toward center)
    red_x = np.clip(x_idx - offset, 0, w - 1)
    result[:, :, 0] = arr[y_idx, red_x, 0]

    # Green stays put (already copied)

    # Blue channel shifts RIGHT by offset (away from center)
    blue_x = np.clip(x_idx + offset, 0, w - 1)
    result[:, :, 2] = arr[y_idx, blue_x, 2]

    return Image.fromarray(result)


def apply_film_grain(img: Image.Image, strength: float = 0.08) -> Image.Image:
    """
    Add film grain/noise overlay for that documentary footage texture.
    """
    arr = np.array(img, dtype=np.float32)

    # Generate noise
    noise = np.random.normal(0, strength * 255, arr.shape).astype(np.float32)

    result = arr + noise
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def apply_vignette(img: Image.Image, strength: float = 0.3) -> Image.Image:
    """
    Darken the edges/corners for a cinematic vignette effect.
    Helps draw focus to center and adds to the ominous mood.
    """
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # Create radial gradient
    y = np.linspace(-1, 1, h).reshape(-1, 1)
    x = np.linspace(-1, 1, w).reshape(1, -1)
    vignette = 1.0 - np.sqrt(x**2 + y**2) * strength
    vignette = np.clip(vignette, 0.3, 1.0)  # Don't go too dark

    vignette = np.broadcast_to(vignette, (h, w))
    for c in range(3):
        arr[:, :, c] *= vignette

    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


class SpeciesPostProcessor:
    """
    Applies the Species channel visual style to generated thumbnails.

    Default preset matches the Screenshake style guide:
    - Bayer dithered backgrounds
    - Red accent glow
    - CRT scan lines
    - Chromatic aberration
    - Film grain
    - Vignette
    """

    # Presets
    PRESETS = {
        "full": {
            "dither": {"enabled": True, "strength": 0.55, "levels": 5},
            "red_glow": {"enabled": True, "strength": 0.2, "position": "bottom"},
            "scanlines": {"enabled": True, "strength": 0.1, "line_width": 2},
            "chromatic_aberration": {"enabled": True, "strength": 4},
            "grain": {"enabled": True, "strength": 0.05},
            "vignette": {"enabled": True, "strength": 0.2},
            "contrast_boost": {"enabled": True, "strength": 1.22},
        },
        "subtle": {
            "dither": {"enabled": True, "strength": 0.4, "levels": 6},
            "red_glow": {"enabled": True, "strength": 0.15, "position": "bottom"},
            "scanlines": {"enabled": True, "strength": 0.06, "line_width": 2},
            "chromatic_aberration": {"enabled": True, "strength": 3},
            "grain": {"enabled": True, "strength": 0.04},
            "vignette": {"enabled": True, "strength": 0.15},
            "contrast_boost": {"enabled": True, "strength": 1.18},
        },
        "heavy": {
            "dither": {"enabled": True, "strength": 0.5, "levels": 5},
            "red_glow": {"enabled": True, "strength": 0.25, "position": "bottom"},
            "scanlines": {"enabled": True, "strength": 0.15, "line_width": 2},
            "chromatic_aberration": {"enabled": True, "strength": 5},
            "grain": {"enabled": True, "strength": 0.08},
            "vignette": {"enabled": True, "strength": 0.25},
            "contrast_boost": {"enabled": True, "strength": 1.25},
        },
        "none": {
            "dither": {"enabled": False},
            "red_glow": {"enabled": False},
            "scanlines": {"enabled": False},
            "chromatic_aberration": {"enabled": False},
            "grain": {"enabled": False},
            "vignette": {"enabled": False},
        },
    }

    def __init__(self, preset: str = "subtle"):
        """Initialize with a preset or custom settings."""
        if preset in self.PRESETS:
            self.settings = self.PRESETS[preset].copy()
        else:
            self.settings = self.PRESETS["subtle"].copy()
        self.preset_name = preset

    def process(self, img: Image.Image) -> Image.Image:
        """
        Apply the full Species post-processing pipeline to an image.

        Order matters — effects are applied in a specific sequence
        to match the Photoshop workflow from the style guide.
        """
        # 1. Bayer dithering (on the base image, especially backgrounds)
        s = self.settings.get("dither", {})
        if s.get("enabled"):
            img = apply_bayer_dither(img, strength=s.get("strength", 0.25), levels=s.get("levels", 8))

        # 2. Red glow (additive, after dither so it gets dithered texture)
        s = self.settings.get("red_glow", {})
        if s.get("enabled"):
            img = apply_red_glow(img, strength=s.get("strength", 0.2), position=s.get("position", "bottom"))

        # 3. Vignette (darken edges)
        s = self.settings.get("vignette", {})
        if s.get("enabled"):
            img = apply_vignette(img, strength=s.get("strength", 0.3))

        # 4. CRT scan lines
        s = self.settings.get("scanlines", {})
        if s.get("enabled"):
            img = apply_crt_scanlines(img, strength=s.get("strength", 0.12), line_width=s.get("line_width", 2))

        # 5. Chromatic aberration (fast version for production)
        s = self.settings.get("chromatic_aberration", {})
        if s.get("enabled"):
            img = apply_chromatic_aberration_fast(img, strength=s.get("strength", 3))

        # 6. Contrast boost (compensate for darkening from scanlines/vignette,
        #    and make subjects POP — Species thumbnails are high contrast)
        s = self.settings.get("contrast_boost", {})
        if s.get("enabled"):
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(s.get("strength", 1.15))

        # 7. Film grain (last — on top of everything)
        s = self.settings.get("grain", {})
        if s.get("enabled"):
            img = apply_film_grain(img, strength=s.get("strength", 0.06))

        return img

    def process_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Process an image file and save the result.
        If output_path is None, overwrites the original.
        Returns the output path.
        """
        img = Image.open(input_path).convert("RGB")
        processed = self.process(img)

        save_path = output_path or input_path

        # Determine format from extension
        ext = Path(save_path).suffix.lower()
        if ext in ('.jpg', '.jpeg'):
            processed.save(save_path, "JPEG", quality=95)
        else:
            processed.save(save_path, "PNG")

        return save_path


# Module-level singleton for easy import
_default_processor = None

def get_processor(preset: str = "subtle") -> SpeciesPostProcessor:
    """Get or create the default processor."""
    global _default_processor
    if _default_processor is None or _default_processor.preset_name != preset:
        _default_processor = SpeciesPostProcessor(preset)
    return _default_processor


def process_thumbnail(file_path: str, preset: str = "subtle") -> str:
    """Convenience function: apply Species post-processing to a thumbnail file."""
    processor = get_processor(preset)
    return processor.process_file(file_path)
