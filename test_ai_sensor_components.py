#!/usr/bin/env python3
"""
AI & Sensor Component Tests for EmberEye
Tests sensor fusion, vision detection, gas sensor, and baseline management
"""
import sys
import os
import numpy as np
import tempfile
import json
from pathlib import Path

# Test results tracking
test_results = {
    'passed': 0,
    'failed': 0,
    'errors': []
}

def log_test(name, passed, error=None):
    """Log test result"""
    if passed:
        test_results['passed'] += 1
        print(f"✓ {name}")
    else:
        test_results['failed'] += 1
        test_results['errors'].append(f"{name}: {error}")
        print(f"✗ {name}: {error}")

def test_sensor_fusion():
    """Test multi-sensor fusion logic"""
    print("\n=== Testing Sensor Fusion ===")
    
    try:
        from sensor_fusion import SensorFusion
        
        # Default fusion requires 2+ sources for alarm (safety feature)
        fusion = SensorFusion()
        
        # Test 1: No sources - no alarm
        result = fusion.fuse()
        log_test("Fusion: No sources = no alarm", 
                not result['alarm'],
                None if not result['alarm'] else f"Alarm with no sources: {result}")
        
        # Test 2: Single source below threshold - no alarm
        result = fusion.fuse(thermal_matrix=[[50]*32 for _ in range(24)])
        log_test("Fusion: Low thermal only = no alarm",
                not result['alarm'],
                None if not result['alarm'] else f"False alarm: {result}")
        
        # Test 3: High temperature alone - no alarm (requires 2+ sources or high confidence)
        hot_matrix = [[200]*32 for _ in range(24)]
        result = fusion.fuse(thermal_matrix=hot_matrix)
        log_test("Fusion: Single high thermal = no alarm (multi-sensor required)",
                not result['alarm'] and 'thermal' in result['sources'],
                None if (not result['alarm'] and 'thermal' in result['sources']) else f"Unexpected: {result}")
        
        # Test 4: High gas alone - no alarm (requires 2+ sources)
        result = fusion.fuse(gas_ppm=2000)  # Well above 400 threshold
        log_test("Fusion: Single high gas = no alarm (multi-sensor required)",
                not result['alarm'] and 'gas' in result['sources'],
                None if (not result['alarm'] and 'gas' in result['sources']) else f"Unexpected: {result}")
        
        # Test 5: Flame alone - no alarm (requires 2+ sources)
        result = fusion.fuse(flame=1)  # 1 = flame detected
        log_test("Fusion: Single flame = no alarm (multi-sensor required)",
                not result['alarm'] and 'flame' in result['sources'],
                None if (not result['alarm'] and 'flame' in result['sources']) else f"Unexpected: {result}")
        
        # Test 6: Multi-source fusion (thermal + gas) - ALARM!
        result = fusion.fuse(
            thermal_matrix=[[180]*32 for _ in range(24)],
            gas_ppm=1500
        )
        log_test("Fusion: Multi-source triggers alarm",
                result['alarm'] and result['confidence'] > 0.5,
                None if (result['alarm'] and result['confidence'] > 0.5) else f"No alarm with 2 sources: {result}")
        
        # Test 7: Hot cells detection
        mixed_matrix = [[50]*32 for _ in range(24)]
        # Add hot spots
        mixed_matrix[10][15] = 220
        mixed_matrix[10][16] = 230
        mixed_matrix[11][15] = 225
        result = fusion.fuse(thermal_matrix=mixed_matrix, gas_ppm=500)  # Add gas for alarm
        has_hot_cells = len(result.get('hot_cells', [])) > 0
        log_test("Fusion: Detects hot cells",
                has_hot_cells,
                None if has_hot_cells else f"No hot cells found: {result}")
        
        # Test 8: Confidence scoring with 3 sources
        result = fusion.fuse(
            thermal_matrix=[[200]*32 for _ in range(24)],
            gas_ppm=2000,
            flame=1
        )
        high_confidence = result.get('confidence', 0) > 0.8
        log_test("Fusion: Three sources = high confidence",
                high_confidence,
                None if high_confidence else f"Confidence too low: {result['confidence']}")
        
        # Test 9: Source tracking
        result = fusion.fuse(thermal_matrix=[[200]*32 for _ in range(24)], gas_ppm=1500)
        sources = result.get('sources', [])
        has_sources = 'thermal' in sources and 'gas' in sources
        log_test("Fusion: Tracks active sources",
                has_sources,
                None if has_sources else f"Missing sources: {sources}")
        
    except Exception as e:
        log_test("Sensor Fusion", False, str(e))

def test_gas_sensor():
    """Test gas sensor calibration and calculations"""
    print("\n=== Testing Gas Sensor ===")
    
    try:
        from gas_sensor import MQ135GasSensor
        
        sensor = MQ135GasSensor()
        
        # Test 1: ADC to PPM conversion
        adc_value = 512  # Mid-range ADC
        ppm = sensor.get_ppm(adc_value, 'CO2')
        log_test("Gas: ADC to PPM conversion",
                ppm > 0 and ppm < 100000,
                None if (ppm > 0 and ppm < 100000) else f"Invalid PPM: {ppm}")
        
        # Test 2: Air Quality Index calculation
        aqi_index, aqi_desc, color = sensor.get_air_quality_index(512)
        log_test("Gas: AQI calculation returns valid index",
                0 <= aqi_index <= 5,
                None if (0 <= aqi_index <= 5) else f"Invalid AQI: {aqi_index}")
        
        log_test("Gas: AQI description exists",
                aqi_desc in ['Good', 'Moderate', 'Unhealthy for Sensitive', 'Unhealthy', 'Very Unhealthy', 'Hazardous'],
                None if aqi_desc else f"No AQI description")
        
        # Test 3: ADC value relationship to gas concentration
        # In MQ-135: Higher ADC = Lower resistance = Higher gas concentration
        high_adc_ppm = sensor.get_ppm(900, 'CO2')  # High ADC = high pollution
        low_adc_ppm = sensor.get_ppm(100, 'CO2')   # Low ADC = low pollution
        log_test("Gas: High ADC (high pollution) > Low ADC (low pollution)",
                high_adc_ppm > low_adc_ppm,
                None if (high_adc_ppm > low_adc_ppm) else f"High ADC PPM={high_adc_ppm}, Low ADC PPM={low_adc_ppm}")
        
        # Test 4: Calibration (R0 calculation)
        if hasattr(sensor, 'calibrate'):
            try:
                sensor.calibrate(512)
                has_r0 = hasattr(sensor, 'r0') and sensor.r0 > 0
                log_test("Gas: Calibration sets R0",
                        has_r0,
                        None if has_r0 else f"Invalid R0: {getattr(sensor, 'r0', None)}")
            except Exception as e:
                log_test("Gas: Calibration", False, str(e))
        
        # Test 5: Different gas types
        if hasattr(sensor, 'gas_curves'):
            co2_ppm = sensor.get_ppm(512, 'CO2')
            co_ppm = sensor.get_ppm(512, 'CO')
            log_test("Gas: Different gas types give different readings",
                    co2_ppm != co_ppm,
                    None if (co2_ppm != co_ppm) else f"CO2={co2_ppm}, CO={co_ppm}")
        
    except Exception as e:
        log_test("Gas Sensor", False, str(e))

def test_vision_detector():
    """Test vision-based fire detection"""
    print("\n=== Testing Vision Detector ===")
    
    try:
        from vision_detector import VisionDetector
        import cv2
        
        detector = VisionDetector()
        
        # Create test frames
        # Test 1: Black frame (no fire)
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        score = detector.detect(black_frame)  # Returns single float score
        log_test("Vision: Black frame = no fire",
                score < 0.3,
                None if score < 0.3 else f"False positive on black: {score}")
        
        # Test 2: Red/orange frame (simulate fire colors)
        fire_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        fire_frame[:, :, 2] = 255  # Red channel
        fire_frame[:, :, 1] = 100  # Some green for orange
        score = detector.detect(fire_frame)
        log_test("Vision: Fire-colored frame increases score",
                score > 0.1,
                None if score > 0.1 else f"No detection on fire colors: {score}")
        
        # Test 3: Score is valid float
        log_test("Vision: Returns valid score",
                isinstance(score, (int, float)) and 0 <= score <= 1,
                None if (isinstance(score, (int, float)) and 0 <= score <= 1) else f"Invalid score: {score}")
        
        # Test 4: Heuristic fire detection
        if hasattr(detector, 'heuristic_fire_smoke'):
            h_score = detector.heuristic_fire_smoke(fire_frame)
            log_test("Vision: Heuristic detection works",
                    isinstance(h_score, (int, float)),
                    None if isinstance(h_score, (int, float)) else f"Invalid heuristic score")
        
        # Test 5: Color analysis for fire
        if hasattr(detector, 'analyze_colors'):
            has_fire_colors = detector.analyze_colors(fire_frame)
            log_test("Vision: Analyzes fire colors",
                    isinstance(has_fire_colors, (bool, float)),
                    None if isinstance(has_fire_colors, (bool, float)) else f"Invalid color analysis")
        
    except Exception as e:
        log_test("Vision Detector", False, str(e))

def test_baseline_manager():
    """Test baseline management for thermal frames"""
    print("\n=== Testing Baseline Manager ===")
    
    try:
        from baseline_manager import BaselineManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = BaselineManager()
            
            # Test 1: Update with normal frame (no change)
            normal_frame = np.ones((24, 32)) * 50
            candidate = manager.update('test_loc', normal_frame)
            log_test("Baseline: Normal frame = no candidate",
                    candidate is None,
                    None if candidate is None else f"False candidate: {candidate}")
            
            # Test 2: Significant change triggers candidate
            hot_frame = np.ones((24, 32)) * 200
            candidate = manager.update('test_loc', hot_frame)
            # First update establishes baseline, second should detect change
            manager.update('test_loc', normal_frame)  # Set baseline
            candidate = manager.update('test_loc', hot_frame)
            has_candidate = candidate is not None or len(manager.candidates) > 0
            log_test("Baseline: Significant change triggers candidate",
                    has_candidate,
                    None if has_candidate else "No candidate on significant change")
            
            # Test 3: Approve candidate
            if manager.candidates:
                loc_id = list(manager.candidates.keys())[0]
                success = manager.approve_candidate(loc_id)
                log_test("Baseline: Approve candidate",
                        success,
                        None if success else f"Failed to approve candidate for {loc_id}")
            
            # Test 4: Persistence (save/load)
            # Change to tmpdir for save operations
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            path_prefix = 'baselines_test'
            manager.save_to_disk(path_prefix=path_prefix)
            # Check if files were created
            npy_files = [f for f in os.listdir(tmpdir) if f.startswith(path_prefix) and f.endswith('.npy')]
            json_file = f'{path_prefix}_events.json'
            has_files = len(npy_files) > 0 or os.path.exists(json_file)
            log_test("Baseline: Save to disk",
                    has_files,
                    None if has_files else f"No files created with prefix {path_prefix}")
            
            # Load in new manager instance
            manager2 = BaselineManager()
            manager2.load_from_disk(path_prefix=path_prefix)
            has_data = len(manager2.baselines) > 0 or len(manager2.events) > 0
            log_test("Baseline: Load from disk",
                    has_data,
                    None if has_data else "No data loaded")
            os.chdir(old_cwd)
            
            # Test 5: Change threshold
            if hasattr(manager, 'change_threshold'):
                old_threshold = manager.change_threshold
                manager.change_threshold = 100
                log_test("Baseline: Threshold configurable",
                        manager.change_threshold == 100,
                        None if manager.change_threshold == 100 else f"Threshold not set: {manager.change_threshold}")
                manager.change_threshold = old_threshold
            
    except Exception as e:
        log_test("Baseline Manager", False, str(e))

def test_error_logger():
    """Test error logging system"""
    print("\n=== Testing Error Logger ===")
    
    try:
        from error_logger import get_error_logger, ErrorLogger
        
        logger = get_error_logger()
        
        # Test 1: Log error
        initial_count = len(logger.get_entries())
        logger.log('TestSource', 'Test error message')
        new_count = len(logger.get_entries())
        log_test("ErrorLogger: Log entry",
                new_count > initial_count,
                None if new_count > initial_count else f"Count unchanged: {initial_count}")
        
        # Test 2: Entry structure
        entries = logger.get_entries()
        if entries:
            entry = entries[-1]
            has_fields = all(k in entry for k in ['timestamp', 'source', 'message'])
            log_test("ErrorLogger: Entry has required fields",
                    has_fields,
                    None if has_fields else f"Missing fields: {entry.keys()}")
        
        # Test 3: Export
        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = os.path.join(tmpdir, 'error_log.json')
            success = logger.export(export_path)
            log_test("ErrorLogger: Export to file",
                    success and os.path.exists(export_path),
                    None if (success and os.path.exists(export_path)) else f"Export failed")
            
            # Validate exported JSON
            if os.path.exists(export_path):
                with open(export_path) as f:
                    exported = json.load(f)
                log_test("ErrorLogger: Exported JSON valid",
                        isinstance(exported, list) and len(exported) > 0,
                        None if isinstance(exported, list) else f"Invalid export: {type(exported)}")
        
        # Test 4: Clear logs
        logger.clear()
        cleared_count = len(logger.get_entries())
        log_test("ErrorLogger: Clear logs",
                cleared_count == 0,
                None if cleared_count == 0 else f"Still has {cleared_count} entries")
        
        # Test 5: Thread safety (basic)
        import threading
        errors_logged = []
        def log_many():
            for i in range(10):
                logger.log('ThreadTest', f'Message {i}')
                errors_logged.append(i)
        
        threads = [threading.Thread(target=log_many) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        final_count = len(logger.get_entries())
        log_test("ErrorLogger: Thread safety",
                final_count >= 30,
                None if final_count >= 30 else f"Lost logs: {final_count}/30")
        
    except Exception as e:
        log_test("Error Logger", False, str(e))

def run_all_tests():
    """Run complete AI/Sensor test suite"""
    print("=" * 60)
    print("EmberEye AI & Sensor Component Tests")
    print("=" * 60)
    
    test_sensor_fusion()
    test_gas_sensor()
    test_vision_detector()
    test_baseline_manager()
    test_error_logger()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {test_results['passed']}")
    print(f"Failed: {test_results['failed']}")
    
    if test_results['errors']:
        print("\nFailed Tests:")
        for error in test_results['errors']:
            print(f"  - {error}")
    
    print("=" * 60)
    
    return test_results['failed'] == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
