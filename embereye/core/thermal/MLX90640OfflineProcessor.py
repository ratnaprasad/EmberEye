import numpy as np
import adafruit_mlx90640

class MLX90640OfflineProcessor:
    """
    Processes MLX90640 EEPROM and raw frame data to produce a 24x32 temperature array.
    Uses the official Adafruit library for all calculations.
    """

    def __init__(self, eeprom_bytes):
        """
        Initialize with the EEPROM data (832 words = 1664 bytes).
        The bytes must be in little‑endian order (LSB first), as they come from the sensor.
        """
        if len(eeprom_bytes) != 1664:
            raise ValueError("EEPROM data must be exactly 1664 bytes (832 words)")

        # Create a dummy I2C device that returns the EEPROM data when read.
        self._dummy_i2c = _DummyI2C(eeprom_bytes)

        # Initialize the Adafruit sensor instance (will read EEPROM via dummy I2C).
        self._sensor = adafruit_mlx90640.MLX90640(self._dummy_i2c)

    def frame_to_temperatures(self, frame_bytes):
        if len(frame_bytes) not in (1664, 1668):
            raise ValueError("Frame data must be 1664 or 1668 bytes")

        frame_words = np.frombuffer(frame_bytes, dtype='<u2')
        frame_data = [int(v) for v in frame_words]

        if len(frame_data) == 832:
            frame_data.extend([0, 0])   # add status/control placeholders
        elif len(frame_data) == 834:
            pass

        # Chess pattern subpage masks (based on row+col parity)
        subpage0_mask = [0] * 768
        subpage1_mask = [0] * 768
        for r in range(24):
            for c in range(32):
                idx = r * 32 + c
                if (r + c) % 2 == 0:
                    subpage0_mask[idx] = 1
                else:
                    subpage1_mask[idx] = 1

        # Create two frame copies with opposite subpages zeroed
        frame0 = frame_data[:]   # for subpage0
        frame1 = frame_data[:]   # for subpage1
        for i in range(768):
            if subpage1_mask[i]:
                frame0[i] = 0
            else:
                frame1[i] = 0

        # Reset the library's internal old frame buffer
        self._sensor._frameDataOld = [0] * 834

        emissivity = 0.95
        result = [0.0] * 768

        # Pass 1: subpage 0
        frame0[832] = 0x0008   # status: new data, subpage 0 last
        tr = self._sensor._GetTa(frame0) - adafruit_mlx90640.OPENAIR_TA_SHIFT
        self._sensor._CalculateTo(frame0, emissivity, tr, result)

        # Pass 2: subpage 1 (old frame now contains frame0)
        frame1[832] = 0x0018   # status: new data, subpage 1 last
        tr = self._sensor._GetTa(frame1) - adafruit_mlx90640.OPENAIR_TA_SHIFT
        self._sensor._CalculateTo(frame1, emissivity, tr, result)

        return np.array(result, dtype=np.float32).reshape((24, 32))

    @staticmethod
    def _s16(x):
        """Convert 16‑bit unsigned to signed."""
        value = int(x)
        return value if value < 32768 else value - 65536


class _DummyI2C:
    """
    A fake I2C device that returns pre‑loaded EEPROM data when the MLX90640 tries to read it.
    This allows us to initialise the Adafruit library without real hardware.
    """
    def __init__(self, eeprom_bytes):
        self._eeprom = eeprom_bytes
        self._locked = False

    def try_lock(self):
        self._locked = True
        return True

    def unlock(self):
        self._locked = False

    def writeto(self, address, buffer, *, start=0, end=None, stop=True):
        # Probe/command writes are accepted as no-ops for offline processing.
        return

    def readfrom_into(self, address, buffer, *, start=0, end=None):
        if end is None:
            end = len(buffer)
        for idx in range(start, end):
            buffer[idx] = 0

    def write_then_readinto(
        self,
        address,
        out_buffer,
        in_buffer,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None,
        stop=False,
    ):
        if out_end is None:
            out_end = len(out_buffer)
        if in_end is None:
            in_end = len(in_buffer)

        command = bytes(memoryview(out_buffer)[out_start:out_end])
        if len(command) >= 2:
            memaddr = (command[0] << 8) | command[1]
        else:
            memaddr = 0

        nbytes = in_end - in_start
        payload = self.readfrom_mem(address, memaddr, nbytes)
        in_buffer[in_start:in_end] = payload

    def writeto_then_readfrom(
        self,
        address,
        out_buffer,
        in_buffer,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None,
        stop=False,
    ):
        self.write_then_readinto(
            address,
            out_buffer,
            in_buffer,
            out_start=out_start,
            out_end=out_end,
            in_start=in_start,
            in_end=in_end,
            stop=stop,
        )

    def readfrom_mem(self, _, memaddr, nbytes):
        # The Adafruit library reads EEPROM starting at address 0x2400.
        # Return the corresponding bytes from our stored EEPROM.
        if 0x2400 <= memaddr <= 0x27FF:
            offset = (memaddr - 0x2400) * 2
            return self._eeprom[offset:offset + nbytes]
        # For any other read (not expected) return zeros.
        return b'\x00' * nbytes