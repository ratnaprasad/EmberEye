"""
Thermal Camera Frame Parser for 32x24 Grid Data

EEPROM Format (once on startup):
- Command: EEPROM1
- Response: #EEPROM1234:<DATA>!
- Total EEPROM data: 832 word blocks (4 chars each) = 3328 chars
- Used for temperature calibration (offset)

Frame Format (continuous streaming):
- Command: PERIODIC_ON (once on startup)
- Response: #frame1234:<DATA>!
- Total raw data: 834 word blocks (4 chars each) = 3336 chars
- Grid data: 24 rows x 32 cols = 768 word blocks = 3072 chars
- EEPROM section: 66 word blocks = 264 chars (INVALID - use EEPROM1 data instead)
"""

import numpy as np
import json
import os


class ThermalFrameParser:
    """Parse thermal camera frames according to sensor datasheet."""
    
    GRID_ROWS = 24
    GRID_COLS = 32
    GRID_WORD_BLOCKS = GRID_ROWS * GRID_COLS  # 768
    FRAME_EEPROM_WORD_BLOCKS = 66  # INVALID section in frames (ignore after EEPROM1)
    FRAME_TOTAL_WORD_BLOCKS = 834  # Frame format: 768 grid + 66 invalid
    EEPROM1_WORD_BLOCKS = 832  # EEPROM1 calibration data blocks
    CHARS_PER_WORD = 4  # FFCB = 4 characters
    
    GRID_DATA_SIZE = GRID_WORD_BLOCKS * CHARS_PER_WORD  # 3072
    FRAME_EEPROM_DATA_SIZE = FRAME_EEPROM_WORD_BLOCKS * CHARS_PER_WORD  # 264 (invalid)
    FRAME_TOTAL_SIZE = FRAME_TOTAL_WORD_BLOCKS * CHARS_PER_WORD  # 3336
    EEPROM1_DATA_SIZE = EEPROM1_WORD_BLOCKS * CHARS_PER_WORD  # 3328

    # Calibration parameters (loaded from config)
    _signed = False
    _scale = 0.01  # raw * scale + offset (deprecated - new protocol uses raw - offset)
    _offset = 0.0
    _calibration_loaded = False
    _use_eeprom = False  # whether to auto-load scale/offset from EEPROM segment
    
    # EEPROM cache for new protocol
    _eeprom_cache = None  # Cached 834-block EEPROM data (3336 chars)
    _eeprom_loaded = False  # Whether EEPROM1 response received this session
    _eeprom_request_sent = False  # Track if EEPROM1 already requested

    @staticmethod
    def _load_calibration():
        if ThermalFrameParser._calibration_loaded:
            return
        cfg_path = os.path.join(os.path.dirname(__file__), 'stream_config.json')
        try:
            with open(cfg_path, 'r') as f:
                cfg = json.load(f)
            calib = cfg.get('thermal_calibration', {})
            ThermalFrameParser._signed = bool(calib.get('signed', False))
            ThermalFrameParser._scale = float(calib.get('scale', 0.01))
            ThermalFrameParser._offset = float(calib.get('offset', 0.0))
            ThermalFrameParser._use_eeprom = bool(cfg.get('thermal_use_eeprom', False))
        except Exception:
            # Keep defaults on error
            pass
        ThermalFrameParser._calibration_loaded = True

    @staticmethod
    def set_calibration(signed: bool = None, scale: float = None, offset: float = None):
        """Programmatically override calibration (runtime adjustments)."""
        if signed is not None:
            ThermalFrameParser._signed = signed
        if scale is not None:
            ThermalFrameParser._scale = scale
        if offset is not None:
            ThermalFrameParser._offset = offset
    
    
    @staticmethod
    def is_eeprom_valid(eeprom_hex: str) -> bool:
        """Validate EEPROM data from raw frame.
        
        Validation checks:
        1. Length: must be exactly 264 chars (66 word blocks × 4 chars)
        2. Content: must contain valid hex characters
        3. Non-zero: at least some blocks must be non-zero (not all 0000)
        
        Returns True if EEPROM is valid and can be used.
        """
        if len(eeprom_hex) != ThermalFrameParser.FRAME_EEPROM_DATA_SIZE:
            print(f"⚠️  EEPROM validation failed: invalid length {len(eeprom_hex)}, expected {ThermalFrameParser.FRAME_EEPROM_DATA_SIZE}")
            return False
        
        try:
            # Check if valid hex
            int(eeprom_hex, 16)
        except ValueError:
            print("⚠️  EEPROM validation failed: contains non-hex characters")
            return False
        
        # Check if not all zeros (at least 10% non-zero blocks)
        non_zero_count = sum(1 for i in range(0, len(eeprom_hex), 4) if eeprom_hex[i:i+4] != "0000")
        if non_zero_count < 7:  # At least 7 out of 66 blocks should be non-zero
            print(f"⚠️  EEPROM validation failed: too many zero blocks ({66 - non_zero_count}/66)")
            return False
        
        return True
    
    @staticmethod
    def needs_eeprom_request() -> bool:
        """Check if EEPROM1 command should be sent.
        
        Returns True if:
        - EEPROM not loaded this session
        - EEPROM request not already sent
        """
        return not ThermalFrameParser._eeprom_loaded and not ThermalFrameParser._eeprom_request_sent
    
    @staticmethod
    def mark_eeprom_requested():
        """Mark that EEPROM1 command has been sent."""
        ThermalFrameParser._eeprom_request_sent = True
    
    @staticmethod
    def reset_eeprom_state():
        """Reset EEPROM state for new connection (called on reconnection)."""
        ThermalFrameParser._eeprom_loaded = False
        ThermalFrameParser._eeprom_request_sent = False
        # Keep cached data in case of temporary disconnect
        print("🔄 EEPROM state reset for new connection")
    
    @staticmethod
    def parse_frame(raw_frame: str) -> dict:
        """
        Parse thermal camera raw frame.
        
        Args:
            raw_frame: Raw hex string (3336 chars) between #frame...: and !
            
        Returns:
            dict with:
                - grid: 24x32 numpy array of temperature values (float, Celsius)
                - eeprom: EEPROM configuration data (hex string)
                - frame_id: Extracted frame ID if present in prefix
        """
        # Remove any whitespace
        raw_frame = raw_frame.replace(" ", "").replace("\n", "").strip()

        if len(raw_frame) != ThermalFrameParser.FRAME_TOTAL_SIZE:
            raise ValueError(
                f"Invalid frame size: {len(raw_frame)} chars, "
                f"expected {ThermalFrameParser.FRAME_TOTAL_SIZE}"
            )
        
        # Extract grid data (first 3072 chars = 768 word blocks)
        grid_hex = raw_frame[:ThermalFrameParser.GRID_DATA_SIZE]
        
        # Extract EEPROM data (remaining 264 chars = 66 word blocks)
        eeprom_hex = raw_frame[ThermalFrameParser.GRID_DATA_SIZE:]
        
        # Load calibration (and config flags) once
        ThermalFrameParser._load_calibration()

        # Validate and potentially apply EEPROM calibration from raw frame
        # Only use raw EEPROM if EEPROM1 not loaded AND validation passes
        if not ThermalFrameParser._eeprom_loaded:
            if ThermalFrameParser.is_eeprom_valid(eeprom_hex):
                if ThermalFrameParser._use_eeprom:
                    ThermalFrameParser._maybe_apply_eeprom(eeprom_hex)
                    print("✅ Using validated EEPROM from raw frame")
            else:
                print("⚠️  Raw EEPROM invalid - parser will request EEPROM1 if calibration needed")

        # Parse grid into 24x32 array using (possibly updated) calibration
        grid = ThermalFrameParser._parse_grid(grid_hex)
        
        return {
            "grid": grid,
            "eeprom": eeprom_hex,
            "rows": ThermalFrameParser.GRID_ROWS,
            "cols": ThermalFrameParser.GRID_COLS
        }
    
    @staticmethod
    def _parse_grid(grid_hex: str) -> np.ndarray:
        """
        Parse 3072-char hex string into 24x32 temperature grid.
        
        Each word block (4 hex chars) represents a temperature reading.
        Format: FFCB -> 0xFFCB -> convert to Celsius
        """
        grid = np.zeros((ThermalFrameParser.GRID_ROWS, ThermalFrameParser.GRID_COLS), dtype=np.float32)
        
        idx = 0
        for row in range(ThermalFrameParser.GRID_ROWS):
            for col in range(ThermalFrameParser.GRID_COLS):
                # Extract 4-char word block
                word_hex = grid_hex[idx:idx + ThermalFrameParser.CHARS_PER_WORD]
                idx += ThermalFrameParser.CHARS_PER_WORD
                
                # Convert hex to int (16-bit value)
                raw_value = int(word_hex, 16)
                
                # Convert to temperature (Celsius)
                # Common MLX90640 conversion: raw_value / 100.0
                # Adjust based on actual sensor calibration
                temp_celsius = ThermalFrameParser._raw_to_celsius(raw_value)
                
                grid[row, col] = temp_celsius
        
        return grid
    
    @staticmethod
    def _raw_to_celsius(raw_value: int) -> float:
        """Convert raw 16-bit sensor value to Celsius using calibration.
        
        Device format: Signed 16-bit centi-degrees with 27°C offset
        Formula: (signed_value / 100.0) + 27.0
        
        Example: 0xFFB0 = 65456 = -80 signed → -80/100 + 27 = 26.20°C
        """
        original_raw = raw_value
        
        # Convert to signed 16-bit (two's complement)
        if raw_value > 0x7FFF:
            signed_value = raw_value - 0x10000
        else:
            signed_value = raw_value
        
        # Convert from centi-degrees to degrees, then add 27°C offset
        temp_celsius = (signed_value / 100.0) + 27.0
        
        # Apply additional offset if configured in stream_config.json
        if ThermalFrameParser._offset != 0.0:
            temp_celsius += ThermalFrameParser._offset
        
        # Debug: Log first value for troubleshooting
        if not hasattr(ThermalFrameParser, '_debug_logged'):
            print(f"🌡️  Temperature Conversion Debug:")
            print(f"   Raw hex: 0x{original_raw:04X} ({original_raw})")
            print(f"   Signed value: {signed_value}")
            print(f"   Centi-degrees: {signed_value / 100.0:.2f}")
            print(f"   Base formula (signed/100 + 27): {(signed_value / 100.0) + 27.0:.2f}°C")
            print(f"   Additional offset: {ThermalFrameParser._offset:.2f}")
            print(f"   Final temp: {temp_celsius:.2f}°C")
            ThermalFrameParser._debug_logged = True
        
        return temp_celsius

    @staticmethod
    def _apply_full_eeprom_calibration(eeprom_hex: str):
        """Apply calibration from full 832-block EEPROM1 data.
        
        Protocol: Use first word (block 0) for offset only.
        Formula: temperature = raw_value - offset
        
        EEPROM1 layout (832 blocks):
          - word[0] (chars 0-3): offset value (signed 16-bit, centi-degrees)
          - word[1-831]: Additional calibration data (currently unused)
        
        Sanity bounds:
          offset range: -100.0 to 100.0°C (allows for device calibration)
        """
        if len(eeprom_hex) < 4:
            return  # need at least one word
        try:
            offset_word = eeprom_hex[0:4]
            raw_offset = int(offset_word, 16)

            # Convert to signed 16-bit
            if raw_offset > 0x7FFF:
                raw_offset -= 0x10000  # two's complement
            
            # Convert to float offset (assuming centi-degrees: 0x0064 = 100 = 1.00°C)
            offset = raw_offset / 100.0

            # Sanity check
            if not (-100.0 <= offset <= 100.0):
                print(f"⚠️ EEPROM offset out of range: {offset:.2f}°C, using default")
                return

            # Apply calibration
            old_offset = ThermalFrameParser._offset
            ThermalFrameParser._offset = offset
            
            # Print detailed calibration info
            print(f"📊 EEPROM CALIBRATION APPLIED:")
            print(f"   ┌─ Raw hex word[0]: 0x{offset_word}")
            print(f"   ├─ Raw signed value: {raw_offset} (centi-degrees)")
            print(f"   ├─ Offset: {offset:.2f}°C")
            print(f"   ├─ Previous offset: {old_offset:.2f}°C")
            print(f"   └─ Temperature correction: raw_value ÷ 100 - {offset:.2f}°C")
            print(f"   ℹ️  Room temp ~28-32°C will display as -0.5 to +5°C (offset-dependent)")
            
        except Exception as e:
            print(f"⚠️ EEPROM calibration parse error: {e}")
            return
    
    @staticmethod
    def _maybe_apply_eeprom(eeprom_hex: str):
        """Legacy fallback for backward compatibility.
        
        NOTE: The 66-word EEPROM section in frames is INVALID after EEPROM1 is loaded.
        This method only used if EEPROM1 command failed or not supported by device.
        """
        # Only use if EEPROM1 not loaded yet (fallback)
        if ThermalFrameParser._eeprom_loaded:
            return  # Ignore 66-word section - use EEPROM1 data instead
        
        if len(eeprom_hex) < 8:
            return
        try:
            # Old protocol: first word is offset (no scale in new protocol)
            offset_word = eeprom_hex[0:4]
            raw_offset = int(offset_word, 16)

            if raw_offset > 0x7FFF:
                raw_offset -= 0x10000
            offset = raw_offset / 100.0

            if not (-100.0 <= offset <= 100.0):
                return

            ThermalFrameParser._offset = offset
        except Exception:
            return
    
    @staticmethod
    def parse_eeprom_packet(packet: str) -> dict:
        """
        Parse EEPROM response packet and cache calibration data.
        
        Packet format: #EEPROM1234:<3336_chars>!\r\n
        Args:
            packet: Raw EEPROM packet string
            
        Returns:
            dict with:
                - success: bool indicating if EEPROM was parsed and cached
                - frame_id: Extracted frame ID (e.g., "1234")
                - blocks: Number of EEPROM blocks parsed (should be 834)
        """
        try:
            # Remove whitespace
            packet = packet.strip()
            
            # Validate format
            if not packet.startswith("#EEPROM"):
                return {"success": False, "error": "Invalid EEPROM packet: must start with #EEPROM"}
            
            # Remove #EEPROM prefix and ! suffix
            content = packet[7:].rstrip("!\r\n")
            
            # Split by colon to get frame_id and data
            if ":" not in content:
                return {"success": False, "error": "Invalid EEPROM packet: missing colon separator"}
            
            frame_id, eeprom_data = content.split(":", 1)
            eeprom_data = eeprom_data.strip()
            
            # Validate size: 832 blocks × 4 chars = 3328 chars
            if len(eeprom_data) != ThermalFrameParser.EEPROM1_DATA_SIZE:
                return {
                    "success": False,
                    "error": f"Invalid EEPROM data size: {len(eeprom_data)} chars, expected {ThermalFrameParser.EEPROM1_DATA_SIZE}",
                    "frame_id": frame_id
                }
            
            # Cache EEPROM data for this session
            ThermalFrameParser._eeprom_cache = eeprom_data
            ThermalFrameParser._eeprom_loaded = True
            
            # Apply calibration from EEPROM (first word: offset only, no scale in new protocol)
            ThermalFrameParser._apply_full_eeprom_calibration(eeprom_data)
            
            print(f"✅ EEPROM1 DATA LOADED:")
            print(f"   ├─ Frame ID: {frame_id}")
            print(f"   ├─ Total size: {len(eeprom_data)} chars (832 blocks)")
            print(f"   ├─ Calibration offset: {ThermalFrameParser._offset:.2f}°C")
            print(f"   └─ Status: Ready for temperature conversion")
            
            return {
                "success": True,
                "frame_id": frame_id,
                "blocks": ThermalFrameParser.EEPROM1_WORD_BLOCKS,
                "chars": len(eeprom_data),
                "offset": ThermalFrameParser._offset
            }
            
        except Exception as e:
            return {"success": False, "error": f"EEPROM parse exception: {e}"}
    
    @staticmethod
    def extract_frame_id(packet: str) -> tuple:
        """
        Extract frame ID and raw data from packet.
        
        Packet format: #frame1234:<DATA>!
        Or: #frame:<DATA>!
        
        Returns:
            (frame_id, raw_data) tuple
        """
        if not packet.startswith("#frame"):
            raise ValueError("Invalid frame packet: must start with #frame")
        
        # Remove #frame prefix and ! suffix
        content = packet[6:].rstrip("!")
        
        # Split by first colon
        if ":" not in content:
            raise ValueError("Invalid frame packet: missing colon separator")
        
        parts = content.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Invalid frame packet format")
        
        frame_id = parts[0]  # Could be loc_id or empty
        raw_data = parts[1]
        
        return frame_id, raw_data


# Example usage and testing
if __name__ == "__main__":
    # Test with sample frame
    sample_raw = "FFCBFFC6FFCBFFBFFFC6FFC0FFC6FFB7FFC1FFB8FFBFFFB2FFBBFFB4FFBEFFB0FFC1FFB2FFC0FFB0FFC2FFB2FFBFFFADFFC2FFB3FFC1FFB0FFC4FFB5FFCFFFB6FFC2FFBBFFB9FFBCFFBBFFB5FFB4FFB3FFB7FFAEFFAEFFAFFFB1FFABFFADFFADFFB8FFAAFFB0FFAEFFB9FFA9FFAFFFADFFB8FFADFFB3FFB0FFBDFFB0FFBDFFB6FFC7FFC1FFC7FFBBFFC0FFBAFFBDFFB2FFB9FFB1FFBAFFAEFFBAFFB0FFBAFFABFFBCFFB0FFBCFFABFFBCFFB1FFBFFFACFFC0FFB0FFC0FFAEFFC1FFB6FFCBFFB1FFBFFFB8FFB4FFB6FFB5FFAFFFABFFAFFFAFFFA8FFAAFFAAFFB0FFA9FFAAFFA9FFB3FFA7FFABFFAAFFB4FFAAFFAEFFACFFBAFFABFFB3FFAFFFBCFFAEFFBAFFAFFFC5FFBEFFC3FFB6FFBDFFB5FFBBFFAEFFB9FFB2FFBAFFADFFB6FFAEFFB7FFA9FFB9FFAFFFB8FFAAFFBCFFB0FFBBFFABFFC1FFB1FFC0FFAFFFC2FFB4FFC5FFB0FFBBFFB2FFAFFFB3FFB3FFAAFFA8FFA9FFADFFA7FFA8FFA8FFADFFA4FFA6FFA7FFB0FFA4FFA7FFA9FFB2FFA6FFACFFAAFFB8FFA9FFB0FFADFFB9FFACFFB7FFADFFC3FFBCFFC1FFB5FFB9FFB4FFB5FFAAFFB4FFAAFFB2FFA5FFB2FFACFFB7FFA8FFB6FFABFFB6FFA9FFBAFFADFFB8FFABFFBDFFAEFFBEFFAEFFBEFFB2FFC4FFADFFB7FFB0FFACFFAFFFADFFA6FFA2FFA6FFA7FF9FFF9DFF9FFFA5FF9FFFA3FFA4FFABFFA1FFA5FFA4FFAEFFA1FFA9FFA8FFB2FFA5FFAFFFACFFB7FFA9FFB5FFAAFFC2FFBBFFBDFFB3FFB6FFB2FFB5FFA9FFB1FFA9FFB0FFA2FFAFFFA7FFB0FFA4FFB5FFAAFFB3FFA5FFB4FFA8FFB6FFA6FFBCFFAEFFBDFFAAFFBEFFB2FFC2FFAAFFB5FFACFFAAFFACFFABFFA5FFA4FFA4FFA7FF9DFF9DFF9FFFA5FF9CFF9DFF9FFFA8FF9EFFA1FFA1FFAAFF9FFFA3FFA4FFB1FFA1FFACFFA9FFB4FFA7FFB2FFA7FFC0FFBBFFBDFFB3FFBAFFB1FFB5FFAAFFB1FFA9FFB5FFA9FFB9FFAEFFB4FFA6FFB3FFA8FFB3FFA4FFB4FFA8FFB7FFA6FFBAFFABFFBBFFACFFBBFFB0FFC3FFA9FFB4FFADFFA8FFACFFAEFFA6FFA1FFA3FFA6FF9EFFA2FFA9FFB5FFACFFA9FFA4FFABFFA0FFA0FFA3FFA7FF9AFFA3FFA3FFB1FFA2FFABFFA6FFB2FFA5FFB2FFA6FFBBFFB9FFB9FFB2FFB9FFB0FFB3FFA8FFB3FFAAFFB8FFB3FFC7FFC0FFC0FFACFFB9FFAFFFB5FFA3FFB2FFA7FFB4FFA5FFB9FFAAFFBBFFABFFBDFFB2FFC3FFAAFFAFFFA9FFA5FFA9FFABFFA2FF9DFFA1FFA6FF9EFFA4FFAEFFBAFFB2FFA8FFA3FFA9FF9EFF9FFF9DFFA8FF9BFFA1FFA1FFAEFFA0FFA7FFA7FFB3FFA6FFB0FFA7FFB6FFB9FFBBFFB1FFB5FFB0FFB3FFAAFFB2FFABFFB6FFAEFFBCFFB8FFB5FFA4FFAEFFA7FFB1FFA3FFB0FFA6FFB2FFA5FFB8FFACFFBAFFABFFBCFFAEFFC1FFABFFA9FFA7FFA3FFA7FFA5FFA0FF9DFFA1FFA5FF9EFF9FFFA6FFACFFA5FF9EFF9CFFA4FF9AFF9CFF9DFFA6FF9AFF9EFF9FFFADFFA0FFA4FFA4FFAFFFA4FFAEFFA3FFBDFFBCFFBAFFB2FFB6FFB0FFB3FFAAFFB2FFABFFB1FFA6FFB0FFA8FFAFFFA3FFB0FFA7FFB0FFA3FFB2FFAAFFB4FFA7FFB8FFAAFFB5FFA9FFB7FFADFFBBFFA8FFADFFA9FFA1FFA8FFA7FFA1FF9CFF9FFFA1FF9AFF9AFF98FFA0FF97FF9AFF9BFFA3FF97FF98FF9CFFA4FF9CFF9DFF9FFFABFF9DFFA1FFA0FFABFFA0FFA8FFA1FFB9FFB9FFB8FFB1FFB2FFB0FFB1FFA8FFB0FFA9FFAEFFA1FFACFFA6FFACFF9FFFB0FFA5FFAFFFA4FFB3FFAAFFB3FFA5FFB2FFA6FFB4FFA5FFB6FFADFFBBFFA8FFA7FFA3FF9EFFA8FFA1FF9DFF9AFF9EFF9EFF97FF97FF9AFF9CFF95FF94FF97FFA0FF97FF98FF9BFFA4FF9AFF9DFF9DFFA6FF97FF9DFF9EFFA8FFA0FFA7FFA3FFB6FFB7FFB7FFB3FFB2FFAFFFB0FFA9FFAEFFA9FFB1FFA4FFAAFFA5FFABFFA2FFB0FFA6FFAFFFA7FFB3FFA9FFB4FFA5FFB3FFA7FFB2FFAAFFB7FFAEFFBCFFAAFFA3FFA1FF9DFFA3FFA0FF9CFF96FF9CFF9CFF97FF92FF98FF9CFF94FF94FF98FFA1FF95FF97FF9DFFA1FF98FF9BFF9DFFA6FF9AFF9DFF9FFFA8FF9FFFA5FFA1FFB8FFB9FFB7FFB2FFB2FFB1FFB2FFA9FFAEFFABFFACFFA7FFADFFA7FFABFFA1FFB2FFAAFFB1FFA6FFB3FFACFFB6FFA7FFB2FFABFFB4FFA8FFB5FFB0FFBBFFACFF9BFF97FF93FF99FF96FF93FF8DFF92FF92FF8FFF8CFF8FFF94FF8AFF8BFF8FFF97FF8EFF90FF94FF9CFF92FF92FF94FF9EFF91FF95FF95FF9FFF97FFA0FF9C4CBD19AA7FFF19AA7FFF19A97FFF19A9FFBFCD3D167FD7A1FFF900090000FFFE197C03F902607FFF197C03F902607FFF00010001000100010001000100010001066A7FFF19AA7FFF19AA7FFF19A97FFFFFC2F4D5CF80D6CF0009FFFCFFFD000100F5003E275A003A00F5003E275A003A0001000100010001000100010001000100010001"
    
    print(f"Sample frame length: {len(sample_raw)} chars")
    print(f"Expected: {ThermalFrameParser.TOTAL_FRAME_SIZE} chars")
    
    try:
        result = ThermalFrameParser.parse_frame(sample_raw)
        print(f"\nParsed successfully!")
        print(f"Grid shape: {result['grid'].shape}")
        print(f"Temperature range: {result['grid'].min():.2f}°C to {result['grid'].max():.2f}°C")
        print(f"EEPROM data length: {len(result['eeprom'])} chars")
        print(f"\nFirst 5x5 grid (top-left corner):")
        print(result['grid'][:5, :5])
    except Exception as e:
        print(f"Parse error: {e}")
