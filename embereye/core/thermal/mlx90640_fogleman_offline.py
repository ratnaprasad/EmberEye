import numpy as np
import MLX90640 as fogleman  # your downloaded file

class MLX90640FoglemanOffline:
    """
    Offline processor using fogleman's MLX90640 library.
    Expects EEPROM and frame bytes in **big‑endian word order** (i.e., the raw hex strings).
    """
    def __init__(self, eeprom_bytes):
        if len(eeprom_bytes) != 1664:
            raise ValueError("EEPROM must be exactly 1664 bytes")
        # Create sensor object without invoking serial-based __init__
        self.sensor = fogleman.MLX90640.__new__(fogleman.MLX90640)
        self.sensor.mem = {}

        # Seed register values required by decode/get_t_o paths
        # 0x800d: adc_resolution(bits10-11)=2 (18-bit), chess_pattern_enabled(bit12)=1
        self.sensor.mem[0x8000] = 0
        self.sensor.mem[0x800d] = (2 << 10) | (1 << 12)
        self.sensor.mem[0x800f] = 0
        self.sensor.reg = self.sensor.decode_registers()

        # Load EEPROM into memory at addresses 0x2400..0x273F
        # Convert each 2‑byte chunk to a big‑endian integer
        for i in range(832):
            addr = 0x2400 + i
            word = int.from_bytes(eeprom_bytes[i*2:i*2+2], 'big')
            self.sensor.mem[addr] = word
        # Decode EEPROM calibration data
        self.sensor.ee = self.sensor.decode_eeprom()

    def frame_to_temperatures(self, frame_bytes):
        if len(frame_bytes) not in (1664, 1668):
            raise ValueError("Frame data must be 1664 or 1668 bytes")
        # Keep only the 832 RAM words used by decode_ram
        if len(frame_bytes) == 1668:
            frame_bytes = frame_bytes[:1664]

        # Load into RAM addresses 0x0400..0x073F (832 words)
        for i in range(832):
            addr = 0x0400 + i
            word = int.from_bytes(frame_bytes[i*2:i*2+2], 'big')
            self.sensor.mem[addr] = word
        # Decode RAM data
        self.sensor.ram = self.sensor.decode_ram()
        # Compute temperatures using the library's internal method
        # The method `get_t_o()` expects the sensor to have ee and ram set
        temps = self.sensor.get_t_o()
        return np.array(temps, dtype=np.float32).reshape((24, 32))