#!/usr/bin/env python3
"""Test script to parse a specific thermal frame and display detailed output."""

from thermal_frame_parser import ThermalFrameParser
import numpy as np

# Raw frame from user
raw_packet = "#frame1234:FFB6FFB0FFB1FF9AFF95FF8DFF8FFF81FF85FF7CFF82FF74FF7CFF72FF7CFF6DFF7EFF6EFF7DFF6CFF7FFF73FF81FF75FF88FF7CFF93FF82FF96FF8DFFB1FF9EFFAEFFA8FFA0FFA0FF89FF82FF7CFF7CFF7AFF73FF70FF6EFF6EFF68FF68FF68FF72FF63FF6BFF68FF76FF67FF71FF70FF80FF73FF81FF80FF8FFF85FF9FFF98FFABFFAAFFADFF9CFF8EFF84FF83FF79FF7AFF75FF77FF6BFF71FF69FF70FF5EFF70FF66FF71FF62FF74FF6BFF7CFF69FF80FF75FF88FF76FF90FF87FF9FFF8CFFA0FF99FF95FF92FF7FFF7AFF73FF73FF6FFF68FF67FF64FF63FF5EFF60FF5CFF65FF58FF60FF5EFF69FF5FFF69FF65FF78FF6AFF7BFF78FF8BFF7DFF8EFF86FF99FF95FF92FF86FF88FF7CFF7FFF71FF76FF6EFF70FF5EFF67FF5FFF65FF57FF67FF5DFF68FF5CFF6EFF62FF6FFF63FF7DFF6DFF82FF74FF8CFF7FFF98FF82FF90FF85FF7CFF7FFF7CFF72FF6DFF6BFF6BFF63FF5CFF59FF5EFF53FF54FF52FF5CFF52FF57FF58FF63FF57FF5EFF5DFF73FF63FF71FF6FFF82FF75FF88FF7EFF93FF8AFF8DFF7FFF7EFF78FF73FF69FF6CFF63FF66FF58FF60FF56FF5EFF51FF5EFF54FF60FF52FF65FF5BFF68FF60FF73FF67FF7FFF6FFF83FF78FF92FF7CFF89FF7FFF77FF78FF72FF69FF5FFF63FF60FF56FF51FF51FF53FF4BFF4BFF4CFF52FF47FF4DFF4DFF5BFF4FFF58FF59FF6AFF5DFF6DFF6AFF79FF6FFF83FF77FF8FFF88FF86FF79FF78FF72FF73FF65FF68FF5BFF60FF54FF5DFF51FF5BFF49FF57FF51FF59FF4EFF5CFF52FF62FF57FF6FFF62FF78FF69FF80FF77FF8EFF7AFF83FF7AFF73FF73FF6BFF64FF5DFF5EFF5CFF4FFF4CFF4DFF52FF44FF45FF42FF4DFF44FF47FF47FF51FF47FF4FFF51FF63FF56FF68FF63FF76FF69FF7CFF76FF8EFF86FF83FF79FF7BFF71FF6CFF61FF62FF5AFF5EFF51FF57FF4DFF54FF47FF54FF48FF56FF4AFF59FF50FF60FF53FF6BFF5DFF76FF66FF7BFF72FF8CFF75FF84FF78FF6EFF70FF6CFF61FF58FF5AFF58FF4CFF4AFF49FF4CFF3EFF41FF3FFF4AFF3AFF44FF44FF4EFF3FFF4EFF4EFF60FF51FF65FF60FF73FF68FF7BFF71FF8BFF86FF80FF75FF76FF6CFF68FF5CFF61FF58FF5AFF4CFF4FFF4AFF51FF46FF53FF48FF51FF44FF57FF4CFF5EFF52FF6AFF5CFF72FF67FF7FFF75FF8CFF77FF7CFF76FF6CFF6DFF67FF5CFF53FF56FF55FF4BFF45FF44FF45FF3AFF3FFF3FFF46FF3DFF3FFF3EFF4CFF42FF4CFF4BFF60FF51FF61FF61FF75FF6BFF79FF72FF85FF83FF81FF78FF72FF6DFF6AFF5FFF61FF59FF59FF4EFF55FF4EFF53FF47FF56FF52FF5DFF52FF5AFF50FF5DFF51FF69FF5FFF74FF65FF7CFF71FF8BFF76FF77FF72FF6CFF6CFF65FF5CFF57FF59FF58FF4CFF4BFF4BFF4EFF47FF49FF4CFF58FF53FF58FF54FF50FF42FF4BFF4DFF60FF52FF61FF5FFF71FF65FF77FF71FF8CFF87FF82FF7AFF78FF6FFF72FF6FFF87FF81FF71FF61FF62FF5CFF60FF55FF5FFF56FF5DFF50FF5DFF58FF62FF58FF6CFF61FF6FFF67FF7AFF73FF87FF77FF7BFF75FF6BFF6FFF68FF5FFF5BFF61FF6BFF60FF54FF4EFF4EFF45FF44FF43FF4CFF42FF46FF47FF52FF4CFF51FF52FF65FF53FF62FF60FF72FF67FF76FF70FF88FF88FF81FF7AFF76FF72FF74FF68FF6BFF64FF63FF59FF5DFF57FF5BFF4EFF5DFF53FF5FFF54FF65FF5EFF6AFF5DFF71FF67FF7AFF6EFF82FF7DFF8CFF7DFF7AFF71FF6AFF70FF68FF61FF5CFF5CFF5DFF52FF4DFF4DFF4FFF45FF45FF47FF51FF47FF49FF4CFF58FF4DFF55FF57FF67FF5BFF66FF68FF77FF70FF7BFF77FF88FF89FF85FF7EFF79FF78FF75FF6BFF6CFF65FF69FF5DFF61FF5CFF61FF57FF62FF5AFF64FF5EFF6BFF61FF70FF64FF78FF6FFF7FFF77FF86FF82FF94FF82FF77FF72FF6DFF70FF6AFF64FF5CFF5DFF5EFF53FF51FF53FF53FF4CFF49FF4DFF55FF49FF4EFF54FF5CFF52FF5BFF5BFF6CFF5EFF68FF6EFF7AFF73FF7EFF7BFF90FF8EFF88FF83FF7FFF80FF7BFF71FF71FF70FF6EFF67FF6BFF64FF69FF5FFF6AFF64FF6CFF62FF73FF6DFF76FF6CFF7CFF75FF82FF7AFF88FF86FF95FF8DFF73FF6FFF67FF6AFF67FF61FF58FF5AFF59FF53FF4EFF50FF56FF49FF4AFF49FF54FF4CFF50FF50FF5CFF53FF59FF59FF68FF5BFF67FF67FF76FF6EFF81FF7F4BC81A017FFF1A017FFF1A007FFF1A00FFBACD3F1634D7A3FFF60008FFFFFFFE19D3040C026E7FFF19D3040D026E7FFF0001000100010001000100010001000106807FFF1A017FFF1A017FFF1A007FFFFFBCF4CCCF7AD6D20008FFFAFFFC00000100004127FF003B0100004127FF003B0001000100010001000100010001000100010001!"

print("="*80)
print("THERMAL FRAME PARSING TEST")
print("="*80)

# Extract frame ID and raw data
frame_id, raw_data = ThermalFrameParser.extract_frame_id(raw_packet)
print(f"\nFrame ID: {frame_id}")
print(f"Raw data length: {len(raw_data)} chars")
print(f"Expected: {ThermalFrameParser.TOTAL_FRAME_SIZE} chars")

# Parse the frame
try:
    result = ThermalFrameParser.parse_frame(raw_data)
    
    print("\n" + "="*80)
    print("PARSE RESULTS")
    print("="*80)
    
    # Grid info
    grid = result['grid']
    print(f"\nGrid shape: {grid.shape} (rows={result['rows']}, cols={result['cols']})")
    print(f"Temperature range: {grid.min():.2f}°C to {grid.max():.2f}°C")
    print(f"Average temperature: {grid.mean():.2f}°C")
    print(f"Std deviation: {grid.std():.2f}°C")
    
    # EEPROM info
    eeprom_hex = result['eeprom']
    print(f"\nEEPROM data length: {len(eeprom_hex)} chars ({len(eeprom_hex)//4} words)")
    
    # Parse first two EEPROM words (stub calibration)
    if len(eeprom_hex) >= 8:
        scale_word = eeprom_hex[0:4]
        offset_word = eeprom_hex[4:8]
        raw_scale = int(scale_word, 16)
        raw_offset = int(offset_word, 16)
        
        scale = raw_scale / 1000.0
        if raw_offset > 0x7FFF:
            raw_offset -= 0x10000
        offset = raw_offset / 100.0
        
        print(f"\nEEPROM Stub Calibration (first 2 words):")
        print(f"  Scale word:  0x{scale_word} = {raw_scale} → scale = {scale:.6f}")
        print(f"  Offset word: 0x{offset_word} = {raw_offset if raw_offset <= 0x7FFF else raw_offset + 0x10000} → offset = {offset:.2f}°C")
        
        # Check if within sanity bounds
        scale_valid = 0.0005 <= scale <= 0.2
        offset_valid = -100.0 <= offset <= 100.0
        print(f"  Scale valid: {scale_valid} (range: 0.0005 to 0.2)")
        print(f"  Offset valid: {offset_valid} (range: -100 to 100)")
        
        if scale_valid and offset_valid:
            print(f"  ✓ EEPROM calibration applied automatically (thermal_use_eeprom=true)")
        else:
            print(f"  ✗ EEPROM calibration REJECTED (out of bounds)")
    
    # Current parser calibration state
    print(f"\nCurrent Parser Calibration:")
    print(f"  Signed: {ThermalFrameParser._signed}")
    print(f"  Scale: {ThermalFrameParser._scale}")
    print(f"  Offset: {ThermalFrameParser._offset}")
    print(f"  Use EEPROM: {ThermalFrameParser._use_eeprom}")
    
    # Sample grid regions
    print("\n" + "="*80)
    print("TEMPERATURE GRID SAMPLES")
    print("="*80)
    
    print("\nTop-left corner (5x5):")
    print(grid[:5, :5])
    
    print("\nCenter region (5x5):")
    center_r = grid.shape[0] // 2
    center_c = grid.shape[1] // 2
    print(grid[center_r-2:center_r+3, center_c-2:center_c+3])
    
    print("\nBottom-right corner (5x5):")
    print(grid[-5:, -5:])
    
    # Hot spots
    print("\n" + "="*80)
    print("HOT SPOT ANALYSIS")
    print("="*80)
    
    hot_threshold = grid.mean() + 1.0 * grid.std()
    hot_cells = np.argwhere(grid > hot_threshold)
    print(f"\nHot cells (> {hot_threshold:.2f}°C): {len(hot_cells)}")
    if len(hot_cells) > 0:
        print("Top 10 hottest cells:")
        flat_temps = grid.flatten()
        top_indices = np.argsort(flat_temps)[-10:][::-1]
        for idx in top_indices:
            row = idx // grid.shape[1]
            col = idx % grid.shape[1]
            temp = grid[row, col]
            print(f"  [{row:2d},{col:2d}] = {temp:.2f}°C")
    
    # Cold spots
    cold_threshold = grid.mean() - 1.0 * grid.std()
    cold_cells = np.argwhere(grid < cold_threshold)
    print(f"\nCold cells (< {cold_threshold:.2f}°C): {len(cold_cells)}")
    if len(cold_cells) > 0:
        print("Top 10 coldest cells:")
        flat_temps = grid.flatten()
        bottom_indices = np.argsort(flat_temps)[:10]
        for idx in bottom_indices:
            row = idx // grid.shape[1]
            col = idx % grid.shape[1]
            temp = grid[row, col]
            print(f"  [{row:2d},{col:2d}] = {temp:.2f}°C")
    
    print("\n" + "="*80)
    print("✓ PARSE COMPLETE")
    print("="*80)
    
except Exception as e:
    print(f"\n✗ PARSE ERROR: {e}")
    import traceback
    traceback.print_exc()
