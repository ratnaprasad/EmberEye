import numpy as np
from pathlib import Path
import sys
# Add the folder to path if needed, or just import the downloaded file
import MLX90640 as fogleman  # assumes the file is named MLX90640.py

class MLX90640FoglemanProcessor:
    """
    Offline processor using fogleman's pure‑Python MLX90640 library.
    Loads EEPROM and frame data from bytes and returns a 24x32 temperature array.
    """
    def __init__(self, eeprom_bytes):
        if len(eeprom_bytes) != 1664:
            raise ValueError("EEPROM must be exactly 1664 bytes")
        # Create a dummy sensor object to hold memory
        self.sensor = fogleman.MLX90640(port=None)  # no serial port
        self.sensor.mem = {}  # ensure fresh dict
        # Load EEPROM into memory at addresses 0x2400..0x273F
        words = self._bytes_to_words_le(eeprom_bytes)
        for i, val in enumerate(words):
            self.sensor.mem[0x2400 + i] = val
        # Decode EEPROM
        self.sensor.ee = self.sensor.decode_eeprom()

    def frame_to_temperatures(self, frame_bytes):
        if len(frame_bytes) not in (1664, 1668):
            raise ValueError("Frame data must be 1664 or 1668 bytes")
        # Ensure 832 words (pad if 834? Actually we'll take first 832 words)
        if len(frame_bytes) == 1668:
            frame_bytes = frame_bytes[:1664]  # drop extra status/control if present
        # Convert to 16‑bit little‑endian integers
        words = self._bytes_to_words_le(frame_bytes)
        # Load into RAM addresses 0x0400..0x073F (832 words)
        for i, val in enumerate(words):
            self.sensor.mem[0x0400 + i] = val
        # Decode RAM
        self.sensor.ram = self.sensor.decode_ram()
        # Compute temperatures using the library's method
        # The library's get_t_o() uses self.ee and self.ram and returns a list of 768 temps
        temps = self.sensor.get_t_o()
        return np.array(temps, dtype=np.float32).reshape((24, 32))

    @staticmethod
    def _bytes_to_words_le(data):
        """Convert little‑endian bytes to a list of 16‑bit integers (native value)."""
        return [int.from_bytes(data[i:i+2], 'little') for i in range(0, len(data), 2)]