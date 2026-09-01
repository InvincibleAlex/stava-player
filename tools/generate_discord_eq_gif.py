from math import pi, sin
from pathlib import Path

from PIL import Image, ImageDraw


BASE_OUTPUT_NAME = "eq-discord-4bars-white-512"
BASE_SIZE = 512
SCALE = 4
FRAME_COUNT = 24
FRAME_DURATION_MS = 40
BACKGROUND = (0, 0, 0, 0)
FOREGROUND = (255, 255, 255, 255)
PREVIEW_DARK_BACKGROUND = (18, 18, 22, 255)
GIF_ALPHA_THRESHOLD = 96


def eased_wave(angle: float) -> float:
    raw = 0.5 + 0.5 * sin(angle)
    return raw * raw * (3.0 - 2.0 * raw)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def smooth_pulse(angle: float, power: float = 2.0) -> float:
    return clamp01(0.5 + 0.5 * sin(angle)) ** power


def musical_level(phase_base: float, bar_index: int) -> float:
    profiles = (
        {
            "main_phase": 0.15,
            "sub_phase": 1.30,
            "accent_phase": 2.10,
            "micro_phase": 0.70,
            "swing_phase": 1.90,
            "weights": (0.22, 0.17, 0.34, 0.18, 0.09),
        },
        {
            "main_phase": 0.95,
            "sub_phase": 0.35,
            "accent_phase": 2.80,
            "micro_phase": 2.10,
            "swing_phase": 0.20,
            "weights": (0.18, 0.22, 0.27, 0.24, 0.09),
        },
        {
            "main_phase": 1.55,
            "sub_phase": 2.20,
            "accent_phase": 0.80,
            "micro_phase": 1.25,
            "swing_phase": 2.60,
            "weights": (0.20, 0.19, 0.31, 0.21, 0.09),
        },
        {
            "main_phase": 2.35,
            "sub_phase": 1.00,
            "accent_phase": 1.55,
            "micro_phase": 2.85,
            "swing_phase": 1.10,
            "weights": (0.16, 0.26, 0.24, 0.24, 0.10),
        },
    )
    profile = profiles[bar_index % len(profiles)]

    main_motion = eased_wave(phase_base + profile["main_phase"])
    sub_motion = eased_wave((phase_base * 2.0) + profile["sub_phase"])
    accent_motion = smooth_pulse((phase_base * 3.0) + profile["accent_phase"], power=3.1)
    micro_motion = smooth_pulse((phase_base * 6.0) + profile["micro_phase"], power=4.2)
    swing_motion = eased_wave((phase_base * 0.5) + profile["swing_phase"])

    w1, w2, w3, w4, w5 = profile["weights"]
    level = (w1 * main_motion) + (w2 * sub_motion) + (w3 * accent_motion) + (w4 * micro_motion) + (w5 * swing_motion)
    level = 0.10 + (0.90 * clamp01(level))
    return clamp01(level)


def energetic_level(phase_base: float, bar_index: int) -> float:
    profiles = (
        {
            "main_phase": 0.05,
            "sub_phase": 1.05,
            "accent_phase": 1.75,
            "micro_phase": 0.50,
            "swing_phase": 2.40,
            "weights": (0.14, 0.18, 0.31, 0.29, 0.08),
        },
        {
            "main_phase": 0.90,
            "sub_phase": 0.15,
            "accent_phase": 2.50,
            "micro_phase": 1.70,
            "swing_phase": 0.65,
            "weights": (0.11, 0.21, 0.27, 0.32, 0.09),
        },
        {
            "main_phase": 1.65,
            "sub_phase": 2.35,
            "accent_phase": 0.65,
            "micro_phase": 2.20,
            "swing_phase": 1.45,
            "weights": (0.13, 0.18, 0.28, 0.31, 0.10),
        },
        {
            "main_phase": 2.15,
            "sub_phase": 0.85,
            "accent_phase": 1.25,
            "micro_phase": 2.75,
            "swing_phase": 2.95,
            "weights": (0.10, 0.19, 0.30, 0.31, 0.10),
        },
    )
    profile = profiles[bar_index % len(profiles)]

    main_motion = eased_wave(phase_base + profile["main_phase"])
    sub_motion = eased_wave((phase_base * 2.0) + profile["sub_phase"])
    accent_motion = smooth_pulse((phase_base * 4.0) + profile["accent_phase"], power=3.6)
    micro_motion = smooth_pulse((phase_base * 8.0) + profile["micro_phase"], power=4.8)
    swing_motion = eased_wave((phase_base * 0.5) + profile["swing_phase"])

    w1, w2, w3, w4, w5 = profile["weights"]
    level = (w1 * main_motion) + (w2 * sub_motion) + (w3 * accent_motion) + (w4 * micro_motion) + (w5 * swing_motion)
    return clamp01(0.08 + (0.92 * level))


def smooth_level(phase_base: float, bar_index: int) -> float:
    profiles = (
        {
            "main_phase": 0.18,
            "sub_phase": 1.47,
            "accent_phase": 2.36,
            "drift_phase": 0.72,
            "weights": (0.38, 0.23, 0.18, 0.21),
        },
        {
            "main_phase": 0.94,
            "sub_phase": 0.28,
            "accent_phase": 2.71,
            "drift_phase": 1.88,
            "weights": (0.34, 0.26, 0.16, 0.24),
        },
        {
            "main_phase": 1.76,
            "sub_phase": 2.18,
            "accent_phase": 0.83,
            "drift_phase": 2.92,
            "weights": (0.36, 0.24, 0.18, 0.22),
        },
        {
            "main_phase": 2.42,
            "sub_phase": 1.06,
            "accent_phase": 1.58,
            "drift_phase": 0.14,
            "weights": (0.33, 0.27, 0.17, 0.23),
        },
    )
    profile = profiles[bar_index % len(profiles)]

    main_motion = eased_wave(phase_base + profile["main_phase"])
    sub_motion = eased_wave((phase_base * 1.37) + profile["sub_phase"])
    accent_motion = smooth_pulse((phase_base * 2.18) + profile["accent_phase"], power=1.85)
    drift_motion = eased_wave((phase_base * 0.63) + profile["drift_phase"])

    w1, w2, w3, w4 = profile["weights"]
    level = (w1 * main_motion) + (w2 * sub_motion) + (w3 * accent_motion) + (w4 * drift_motion)
    return clamp01(0.04 + (0.94 * level))


def make_rgba_from_mask(mask: Image.Image) -> Image.Image:
    image = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    image.putalpha(mask)
    return image


def make_gif_frame(rgba_image: Image.Image) -> Image.Image:
    alpha = rgba_image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value >= GIF_ALPHA_THRESHOLD else 0, mode="L")

    frame = Image.new("P", rgba_image.size, 0)
    frame.putpalette([
        0, 0, 0,
        255, 255, 255,
    ] + [0, 0, 0] * 254)
    frame.paste(1, mask=mask)
    frame.info["transparency"] = 0
    frame.info["disposal"] = 2
    return frame


def make_frame(frame_index: int, level_builder, min_ratio: float = 0.11, max_ratio: float = 0.28) -> Image.Image:
    size = BASE_SIZE * SCALE
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    bar_width = 52 * SCALE
    gap = 32 * SCALE
    radius = 26 * SCALE
    total_width = (bar_width * 4) + (gap * 3)
    start_x = (size - total_width) // 2
    center_y = size // 2
    min_half_height = int(size * min_ratio)
    max_half_height = int(size * max_ratio)
    phase_base = (2.0 * pi * frame_index) / FRAME_COUNT
    for index in range(4):
        level = level_builder(phase_base, index)
        half_height = int(min_half_height + (max_half_height - min_half_height) * level)
        x0 = start_x + index * (bar_width + gap)
        y0 = center_y - half_height
        x1 = x0 + bar_width
        y1 = center_y + half_height
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)

    mask = mask.resize((BASE_SIZE, BASE_SIZE), Image.Resampling.LANCZOS)
    return make_rgba_from_mask(mask)


def build_variant_assets(output_dir: Path, suffix: str, level_builder, min_ratio: float, max_ratio: float) -> tuple[Path, Path, Path]:
    output_stem = f"{BASE_OUTPUT_NAME}-{suffix}"
    gif_path = output_dir / f"{output_stem}.gif"
    preview_path = output_dir / f"{output_stem}-preview.png"
    preview_dark_path = output_dir / f"{output_stem}-preview-dark.png"

    frames = [make_frame(index, level_builder, min_ratio=min_ratio, max_ratio=max_ratio) for index in range(FRAME_COUNT)]
    gif_frames = [make_gif_frame(frame) for frame in frames]

    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        format="GIF",
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        transparency=0,
        optimize=False,
    )
    frames[0].save(preview_path, format="PNG")
    preview_dark = Image.new("RGBA", frames[0].size, PREVIEW_DARK_BACKGROUND)
    preview_dark.alpha_composite(frames[0])
    preview_dark.save(preview_dark_path, format="PNG")
    return gif_path, preview_path, preview_dark_path


def build_assets() -> list[tuple[Path, Path, Path]]:
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "icons" / "player"
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = [
        ("energetic", energetic_level, 0.08, 0.34),
        ("smooth", smooth_level, 0.04, 0.38),
    ]
    return [build_variant_assets(output_dir, suffix, builder, min_ratio, max_ratio) for suffix, builder, min_ratio, max_ratio in variants]


if __name__ == "__main__":
    for gif_path, preview_path, preview_dark_path in build_assets():
        print(gif_path)
        print(preview_path)
        print(preview_dark_path)