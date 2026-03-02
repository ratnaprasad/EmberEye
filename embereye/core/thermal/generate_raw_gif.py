from pathlib import Path
from datetime import datetime
import numpy as np
from PIL import Image, ImageDraw

from mlx90640_fogleman_offline import MLX90640FoglemanOffline


def read_first_hex_line(path: Path) -> str:
    for line in path.read_text().splitlines():
        text = line.strip()
        if text and all(char in "0123456789abcdefABCDEF" for char in text):
            return text
    raise RuntimeError(f"No hex line found in {path}")


def read_frame_hex_lines(path: Path) -> list[str]:
    frames: list[str] = []
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text:
            continue
        if all(char in "0123456789abcdefABCDEF" for char in text) and len(text) >= 3300:
            frames.append(text)
    return frames


def normalize_to_u8(values: np.ndarray, minimum: float, maximum: float) -> np.ndarray:
    if maximum <= minimum:
        normalized = np.zeros_like(values, dtype=np.float32)
    else:
        normalized = (values - minimum) / (maximum - minimum)
    normalized = np.clip(normalized, 0.0, 1.0)
    return (normalized * 255.0).astype(np.uint8)


def inferno_lut() -> np.ndarray:
    anchors = np.array(
        [
            [0, 0, 4],
            [30, 12, 95],
            [120, 28, 109],
            [187, 55, 84],
            [249, 142, 8],
            [252, 255, 164],
        ],
        dtype=np.float32,
    )
    anchor_x = np.linspace(0, 255, len(anchors), dtype=np.float32)
    x_values = np.arange(256, dtype=np.float32)
    return np.stack(
        [
            np.interp(x_values, anchor_x, anchors[:, 0]),
            np.interp(x_values, anchor_x, anchors[:, 1]),
            np.interp(x_values, anchor_x, anchors[:, 2]),
        ],
        axis=1,
    ).astype(np.uint8)


def to_rgb_gray(gray: np.ndarray) -> np.ndarray:
    return np.stack([gray, gray, gray], axis=2)


def upscale_rgb(rgb: np.ndarray, scale: int = 8) -> Image.Image:
    return Image.fromarray(rgb, mode="RGB").resize((32 * scale, 24 * scale), Image.Resampling.NEAREST)


def compose_top3_frame(gray_rgb: np.ndarray, inferno_rgb: np.ndarray, delta_rgb: np.ndarray, scale: int = 8) -> Image.Image:
    left = upscale_rgb(gray_rgb, scale)
    mid = upscale_rgb(inferno_rgb, scale)
    right = upscale_rgb(delta_rgb, scale)

    panel_w, panel_h = left.size
    header_h = 20
    canvas = Image.new("RGB", (panel_w * 3, panel_h + header_h), (0, 0, 0))
    canvas.paste(left, (0, header_h))
    canvas.paste(mid, (panel_w, header_h))
    canvas.paste(right, (panel_w * 2, header_h))

    draw = ImageDraw.Draw(canvas)
    draw.text((6, 4), "Radiometric Gray", fill=(255, 255, 255))
    draw.text((panel_w + 6, 4), "Inferno", fill=(255, 255, 255))
    draw.text((panel_w * 2 + 6, 4), "Temporal Delta", fill=(255, 255, 255))
    return canvas


def main() -> None:
    thermal_dir = Path(__file__).resolve().parent
    testdata_dir = thermal_dir / "testdata"

    eeprom_hex = read_first_hex_line(testdata_dir / "EEPROM DATA.txt")
    eeprom_bytes = bytes.fromhex(eeprom_hex)

    frame_hex_lines = read_frame_hex_lines(testdata_dir / "RAW FRAME DATA.txt")
    if not frame_hex_lines:
        raise RuntimeError("No frame hex blocks found in RAW FRAME DATA.txt")

    processor = MLX90640FoglemanOffline(eeprom_bytes)

    temperatures: list[np.ndarray] = []
    for frame_hex in frame_hex_lines:
        frame_bytes = bytes.fromhex(frame_hex)
        if len(frame_bytes) > 1668:
            frame_bytes = frame_bytes[:1668]
        elif len(frame_bytes) not in (1664, 1668):
            continue
        temperatures.append(processor.frame_to_temperatures(frame_bytes))

    if not temperatures:
        raise RuntimeError("No valid frames decoded")

    all_values = np.concatenate([temp[np.isfinite(temp)] for temp in temperatures])
    temp_min = float(np.min(all_values))
    temp_max = float(np.max(all_values))

    lut = inferno_lut()

    deltas: list[np.ndarray] = []
    prev = temperatures[0]
    for current in temperatures:
        deltas.append(np.abs(current - prev))
        prev = current
    all_delta_values = np.concatenate([delta[np.isfinite(delta)] for delta in deltas])
    delta_min = 0.0
    delta_max = float(np.max(all_delta_values)) if all_delta_values.size else 1.0
    if delta_max <= 0.0:
        delta_max = 1.0

    inferno_frames: list[Image.Image] = []
    top3_frames: list[Image.Image] = []
    for temp, delta in zip(temperatures, deltas):
        gray = normalize_to_u8(temp, temp_min, temp_max)
        inferno = lut[gray]

        delta_gray = normalize_to_u8(delta, delta_min, delta_max)
        delta_inferno = lut[delta_gray]

        inferno_frames.append(upscale_rgb(inferno, scale=8))
        top3_frames.append(
            compose_top3_frame(
                gray_rgb=to_rgb_gray(gray),
                inferno_rgb=inferno,
                delta_rgb=delta_inferno,
                scale=8,
            )
        )

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = thermal_dir / "generated_images" / f"continuous_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_gif = output_dir / "raw_frame_data_animation.gif"
    output_top3_gif = output_dir / "raw_frame_data_animation_top3.gif"

    inferno_frames[0].save(
        output_gif,
        save_all=True,
        append_images=inferno_frames[1:],
        duration=250,
        loop=0,
        optimize=False,
    )

    top3_frames[0].save(
        output_top3_gif,
        save_all=True,
        append_images=top3_frames[1:],
        duration=250,
        loop=0,
        optimize=False,
    )

    print(f"Frames parsed   : {len(frame_hex_lines)}")
    print(f"Frames decoded  : {len(temperatures)}")
    print(f"Temperature span: {temp_min:.2f}C .. {temp_max:.2f}C")
    print(f"Inferno GIF     : {output_gif}")
    print(f"Top3 GIF        : {output_top3_gif}")


if __name__ == "__main__":
    main()
