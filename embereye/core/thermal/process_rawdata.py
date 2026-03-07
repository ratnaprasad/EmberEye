import numpy as np
from pathlib import Path
from datetime import datetime
import uuid
from PIL import Image

try:
    from embereye.core.thermal.mlx90640_fogleman_offline import MLX90640FoglemanOffline as MLX90640Direct
except Exception:
    from mlx90640_fogleman_offline import MLX90640FoglemanOffline as MLX90640Direct


def _normalize_to_u8(temperatures, valid_mask):
    if valid_mask.any():
        t_min = float(np.min(temperatures[valid_mask]))
        t_max = float(np.max(temperatures[valid_mask]))
    else:
        t_min = float(np.min(temperatures))
        t_max = float(np.max(temperatures))

    if t_max <= t_min:
        norm = np.zeros_like(temperatures, dtype=np.float32)
    else:
        norm = (temperatures - t_min) / (t_max - t_min)
        norm = np.clip(norm, 0.0, 1.0)

    gray = (norm * 255.0).astype(np.uint8)
    gray = np.where(valid_mask, gray, 0).astype(np.uint8)
    return gray


def _palette_lut(name):
    if name == 'inferno':
        anchors = np.array([
            [0, 0, 4],
            [30, 12, 95],
            [120, 28, 109],
            [187, 55, 84],
            [249, 142, 8],
            [252, 255, 164],
        ], dtype=np.float32)
    else:  # jet-like palette
        anchors = np.array([
            [0, 0, 128],
            [0, 128, 255],
            [0, 255, 255],
            [255, 255, 0],
            [255, 128, 0],
            [128, 0, 0],
        ], dtype=np.float32)

    anchor_x = np.linspace(0, 255, len(anchors), dtype=np.float32)
    x = np.arange(256, dtype=np.float32)
    lut = np.stack([
        np.interp(x, anchor_x, anchors[:, 0]),
        np.interp(x, anchor_x, anchors[:, 1]),
        np.interp(x, anchor_x, anchors[:, 2]),
    ], axis=1).astype(np.uint8)
    return lut


def _apply_palette(gray_u8, palette_name):
    lut = _palette_lut(palette_name)
    return lut[gray_u8]


def _save_pgm(path, gray_u8):
    h, w = gray_u8.shape
    with open(path, 'wb') as out:
        out.write(f"P5\n{w} {h}\n255\n".encode('ascii'))
        out.write(gray_u8.tobytes())


def _save_ppm(path, rgb_u8):
    h, w, _ = rgb_u8.shape
    with open(path, 'wb') as out:
        out.write(f"P6\n{w} {h}\n255\n".encode('ascii'))
        out.write(rgb_u8.tobytes())


def _save_png_gray(path, gray_u8):
    Image.fromarray(gray_u8, mode='L').save(path)


def _save_png_rgb(path, rgb_u8):
    Image.fromarray(rgb_u8, mode='RGB').save(path)


def _draw_cross(rgb, row, col, color=(255, 255, 255), radius=2):
    h, w, _ = rgb.shape
    for dx in range(-radius, radius + 1):
        c = col + dx
        if 0 <= c < w and 0 <= row < h:
            rgb[row, c] = color
    for dy in range(-radius, radius + 1):
        r = row + dy
        if 0 <= r < h and 0 <= col < w:
            rgb[r, col] = color


def generate_thermal_images(temperatures, valid_mask, ppm_pgm_dir, png_dir, run_id):
    ppm_pgm_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)
    gray = _normalize_to_u8(temperatures, valid_mask)
    inferno = _apply_palette(gray, 'inferno')
    jet = _apply_palette(gray, 'jet')

    # 1) Absolute temperature grayscale
    _save_pgm(ppm_pgm_dir / f"thermal_grayscale_{run_id}.pgm", gray)
    _save_png_gray(png_dir / f"thermal_grayscale_{run_id}.png", gray)

    # 2) False-color inferno
    _save_ppm(ppm_pgm_dir / f"thermal_inferno_{run_id}.ppm", inferno)
    _save_png_rgb(png_dir / f"thermal_inferno_{run_id}.png", inferno)

    # 3) False-color jet
    _save_ppm(ppm_pgm_dir / f"thermal_jet_{run_id}.ppm", jet)
    _save_png_rgb(png_dir / f"thermal_jet_{run_id}.png", jet)

    # 4) Binary hot mask
    if valid_mask.any():
        hot_threshold = float(np.percentile(temperatures[valid_mask], 85))
    else:
        hot_threshold = float(np.max(temperatures))
    hot_mask = np.where((temperatures >= hot_threshold) & valid_mask, 255, 0).astype(np.uint8)
    _save_pgm(ppm_pgm_dir / f"thermal_hot_mask_{run_id}.pgm", hot_mask)
    _save_png_gray(png_dir / f"thermal_hot_mask_{run_id}.png", hot_mask)

    # 5) Multi-band segmentation
    segmented = np.zeros((*temperatures.shape, 3), dtype=np.uint8)
    if valid_mask.any():
        v = temperatures[valid_mask]
        q1, q2, q3 = np.percentile(v, [25, 50, 75])
        band0 = valid_mask & (temperatures < q1)
        band1 = valid_mask & (temperatures >= q1) & (temperatures < q2)
        band2 = valid_mask & (temperatures >= q2) & (temperatures < q3)
        band3 = valid_mask & (temperatures >= q3)
        segmented[band0] = (0, 0, 128)
        segmented[band1] = (0, 200, 255)
        segmented[band2] = (255, 200, 0)
        segmented[band3] = (255, 0, 0)
    _save_ppm(ppm_pgm_dir / f"thermal_multiband_{run_id}.ppm", segmented)
    _save_png_rgb(png_dir / f"thermal_multiband_{run_id}.png", segmented)

    # 6) Hotspot annotation image
    annotated = inferno.copy()
    if valid_mask.any():
        valid_min_idx = np.unravel_index(np.argmin(np.where(valid_mask, temperatures, np.inf)), temperatures.shape)
        valid_max_idx = np.unravel_index(np.argmax(np.where(valid_mask, temperatures, -np.inf)), temperatures.shape)
        _draw_cross(annotated, valid_min_idx[0], valid_min_idx[1], color=(0, 255, 255), radius=2)
        _draw_cross(annotated, valid_max_idx[0], valid_max_idx[1], color=(255, 255, 255), radius=2)
    _save_ppm(ppm_pgm_dir / f"thermal_hotspots_{run_id}.ppm", annotated)
    _save_png_rgb(png_dir / f"thermal_hotspots_{run_id}.png", annotated)

    # 7) Isotherm-style contour overlay
    contours = inferno.copy()
    levels = [32, 64, 96, 128, 160, 192, 224]
    for level in levels:
        edge = np.abs(gray.astype(np.int16) - level) <= 1
        contours[edge & valid_mask] = (255, 255, 255)
    _save_ppm(ppm_pgm_dir / f"thermal_isotherm_{run_id}.ppm", contours)
    _save_png_rgb(png_dir / f"thermal_isotherm_{run_id}.png", contours)

    # 8) Valid-pixel map
    valid_map = np.where(valid_mask, 255, 0).astype(np.uint8)
    _save_pgm(ppm_pgm_dir / f"thermal_valid_map_{run_id}.pgm", valid_map)
    _save_png_gray(png_dir / f"thermal_valid_map_{run_id}.png", valid_map)

def read_hex_file(filename, swap_word_bytes=False):
    """Read a file that contains a header line and then a hex string."""
    with open(filename, 'r') as f:
        lines = f.readlines()
        # The hex data is usually on the second line (skip the header)
        for line in lines:
            line = line.strip()
            if line and not line.startswith('EEPROM') and not line.startswith('FFB6'):
                # It's the hex data line
                hex_str = line
                break
        else:
            # Fallback: take the first line that looks like hex
            for line in lines:
                line = line.strip()
                if all(c in '0123456789ABCDEFabcdef' for c in line):
                    hex_str = line
                    break
            else:
                raise ValueError("No hex string found in file")

    data = bytes.fromhex(hex_str)
    if len(data) % 2 != 0:
        raise ValueError(f"Hex data in {filename} has odd byte length: {len(data)}")

    if swap_word_bytes:
        # Some frame dumps are stored as 16-bit words in big-endian textual order
        # (e.g., FFB6). Convert each word to little-endian bytes for numpy '<u2' parsing.
        data = b''.join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data), 2))
    return data

def main():
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]

    # Read the files
    thermal_dir = Path(__file__).resolve().parent
    testdata_dir = thermal_dir / 'testdata'
    generated_images_dir = thermal_dir / 'generated_images' / run_id
    ppm_pgm_dir = generated_images_dir / 'ppm_pgm'
    png_dir = generated_images_dir / 'png'
    csv_dir = thermal_dir / 'csvfolder'
    csv_dir.mkdir(parents=True, exist_ok=True)

    eeprom_bytes = read_hex_file(testdata_dir / 'EEPROM DATA.txt', swap_word_bytes=False)
    frame_bytes = read_hex_file(testdata_dir / 'RAW FRAME DATA- HUMAN PRESENCE.txt', swap_word_bytes=False)

    print(f"EEPROM loaded: {len(eeprom_bytes)} bytes")
    print(f"Frame loaded : {len(frame_bytes)} bytes")

    if len(frame_bytes) > 1668:
        print(f"Trimming frame from {len(frame_bytes)} to 1668 bytes")
        frame_bytes = frame_bytes[:1668]
    elif len(frame_bytes) not in (1664, 1668):
        raise ValueError(f"Unsupported frame data length: {len(frame_bytes)} bytes (expected 1664 or 1668)")

    # Create processor and compute temperatures
    processor = MLX90640Direct(eeprom_bytes)
    temperatures = processor.frame_to_temperatures(frame_bytes)

    # Print results
    print(f"\nTemperature range: {temperatures.min():.2f}°C to {temperatures.max():.2f}°C")
    print(f"Average: {temperatures.mean():.2f}°C")

    total_pixels = temperatures.size
    zero_mask = temperatures == 0.0
    valid_mask = np.isfinite(temperatures) & ~zero_mask
    zero_count = int(zero_mask.sum())
    valid_count = int(valid_mask.sum())
    invalid_count = int((~np.isfinite(temperatures)).sum())

    min_idx = np.unravel_index(np.argmin(temperatures), temperatures.shape)
    max_idx = np.unravel_index(np.argmax(temperatures), temperatures.shape)

    print("\nSanity report:")
    print(f"  Total pixels : {total_pixels}")
    print(f"  Valid pixels : {valid_count} ({(valid_count / total_pixels) * 100:.1f}%)")
    print(f"  Zero pixels  : {zero_count} ({(zero_count / total_pixels) * 100:.1f}%)")
    print(f"  NaN/Inf      : {invalid_count}")
    print(f"  Global min   : {temperatures[min_idx]:.2f}°C at (row={min_idx[0]}, col={min_idx[1]})")
    print(f"  Global max   : {temperatures[max_idx]:.2f}°C at (row={max_idx[0]}, col={max_idx[1]})")

    if valid_count > 0:
        valid_min_idx = np.unravel_index(np.argmin(np.where(valid_mask, temperatures, np.inf)), temperatures.shape)
        valid_max_idx = np.unravel_index(np.argmax(np.where(valid_mask, temperatures, -np.inf)), temperatures.shape)
        print(f"  Valid min    : {temperatures[valid_min_idx]:.2f}°C at (row={valid_min_idx[0]}, col={valid_min_idx[1]})")
        print(f"  Valid max    : {temperatures[valid_max_idx]:.2f}°C at (row={valid_max_idx[0]}, col={valid_max_idx[1]})")

    print("\nFirst 5x5 corner (top‑left):")
    print(temperatures[:5, :5])

    generate_thermal_images(temperatures, valid_mask, ppm_pgm_dir, png_dir, run_id)
    print(f"\nPPM/PGM images saved to: {ppm_pgm_dir}")
    print(f"PNG images saved to: {png_dir}")

    csv_path = csv_dir / f"temperatures_{run_id}.csv"
    np.savetxt(csv_path, temperatures, delimiter=',', fmt='%.2f')
    print(f"Temperatures saved to: {csv_path}")

if __name__ == '__main__':
    main()