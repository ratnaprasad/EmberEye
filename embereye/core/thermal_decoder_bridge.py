from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any
import sys


THERMAL_DIR = Path(__file__).resolve().parent / "thermal"
if str(THERMAL_DIR) not in sys.path:
    sys.path.insert(0, str(THERMAL_DIR))

try:
    # Preferred runtime wiring: process_rawdata exposes MLX90640Direct alias
    # which points to MLX90640FoglemanOffline in thermal package.
    from process_rawdata import MLX90640Direct as ThermalRuntimeProcessor
except Exception:
    # Fallback to direct class import if process_rawdata module is unavailable.
    from mlx90640_fogleman_offline import MLX90640FoglemanOffline as ThermalRuntimeProcessor


EEPROM_WORDS = 832
EEPROM_HEX_LEN = EEPROM_WORDS * 4
FRAME_WORDS = 834
FRAME_HEX_LEN = FRAME_WORDS * 4
GRID_WORDS = 768
GRID_HEX_LEN = GRID_WORDS * 4

_DEFAULT_EEPROM_HEX: Optional[str] = None
_PROCESSOR_CACHE: Dict[str, Any] = {}


def _clean_hex(text: str) -> str:
    return "".join(ch for ch in (text or "") if ch in "0123456789abcdefABCDEF")


def _is_hex(text: str) -> bool:
    return bool(text) and all(ch in "0123456789abcdefABCDEF" for ch in text)


def _first_hex_line(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    for line in path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if _is_hex(stripped):
            return stripped
    return None


def get_default_eeprom_hex() -> Optional[str]:
    global _DEFAULT_EEPROM_HEX
    if _DEFAULT_EEPROM_HEX is not None:
        return _DEFAULT_EEPROM_HEX

    candidate = THERMAL_DIR / "testdata" / "EEPROM DATA.txt"
    hex_line = _first_hex_line(candidate)
    if hex_line and len(hex_line) >= EEPROM_HEX_LEN:
        _DEFAULT_EEPROM_HEX = hex_line[:EEPROM_HEX_LEN]
        return _DEFAULT_EEPROM_HEX
    return None


def parse_eeprom_packet(packet: str) -> Dict[str, Any]:
    packet = (packet or "").strip()
    if not packet.startswith("#EEPROM"):
        return {"success": False, "error": "not_eeprom"}

    content = packet[7:].rstrip("!\r\n")
    if ":" not in content:
        return {"success": False, "error": "missing_colon"}

    frame_id, payload = content.split(":", 1)
    eeprom_hex = _clean_hex(payload)
    if len(eeprom_hex) < EEPROM_HEX_LEN:
        return {
            "success": False,
            "error": f"short_eeprom:{len(eeprom_hex)}",
            "frame_id": frame_id,
        }

    eeprom_hex = eeprom_hex[:EEPROM_HEX_LEN]
    return {
        "success": True,
        "frame_id": frame_id,
        "blocks": EEPROM_WORDS,
        "hex": eeprom_hex,
    }


def _get_processor(eeprom_hex: str):
    cached = _PROCESSOR_CACHE.get(eeprom_hex)
    if cached is not None:
        return cached
    processor = ThermalRuntimeProcessor(bytes.fromhex(eeprom_hex))
    _PROCESSOR_CACHE[eeprom_hex] = processor
    return processor


def decode_frame_to_matrix(frame_hex: str, eeprom_hex: Optional[str] = None, fallback_eeprom_hex: Optional[str] = None) -> Dict[str, Any]:
    clean = _clean_hex(frame_hex)
    if len(clean) < FRAME_HEX_LEN:
        return {"success": False, "error": f"short_frame:{len(clean)}"}

    frame_bytes = bytes.fromhex(clean[:FRAME_HEX_LEN])

    selected_eeprom = None
    eeprom_source = "none"
    for candidate, source in ((eeprom_hex, "device"), (fallback_eeprom_hex, "cached"), (get_default_eeprom_hex(), "default")):
        if candidate and len(candidate) >= EEPROM_HEX_LEN:
            selected_eeprom = candidate[:EEPROM_HEX_LEN]
            eeprom_source = source
            break

    if not selected_eeprom:
        return {"success": False, "error": "no_eeprom"}

    try:
        processor = _get_processor(selected_eeprom)
        matrix = processor.frame_to_temperatures(frame_bytes)
        return {
            "success": True,
            "matrix": matrix.tolist(),
            "rows": 24,
            "cols": 32,
            "eeprom_source": eeprom_source,
        }
    except Exception as exc:
        return {"success": False, "error": f"decode_failed:{exc}", "eeprom_source": eeprom_source}
