#!/usr/bin/env python3
"""
Comprehensive Test Suite for EmberEye
Tests TCP server parsing, resolver, PFDS, logging, and integration
"""
import sys
import os
import socket
import time
import json
import sqlite3
import tempfile
import shutil
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

def test_tcp_packet_parsing():
    """Test TCP packet parsing with various formats"""
    print("\n=== Testing TCP Packet Parsing ===")
    
    try:
        from tcp_sensor_server import TCPSensorServer
        
        # Test data collector
        received_packets = []
        
        def packet_callback(packet):
            received_packets.append(packet)
        
        server = TCPSensorServer(port=9001, packet_callback=packet_callback)
        
        # Test parser directly
        test_cases = [
            {
                'name': 'Serialno packet',
                'packet': '#serialno:123456!',
                'expected_type': 'serialno',
                'check': lambda p: p.get('serialno') == '123456'
            },
            {
                'name': 'Loc_id packet',
                'packet': '#locid:test room!',
                'expected_type': 'locid',
                'check': lambda p: p.get('loc_id') == 'test room'
            },
            {
                'name': 'Sensor separate format',
                'packet': '#Sensor:room1:ADC1=100,ADC2=200!',
                'expected_type': 'sensor',
                'check': lambda p: p.get('loc_id') == 'room1' and p.get('ADC1') == 100
            },
            {
                'name': 'Sensor embedded format',
                'packet': '#Sensor123:ADC1=300,ADC2=400!',
                'expected_type': 'sensor',
                'check': lambda p: p.get('loc_id') == '123' and p.get('ADC1') == 300
            },
            {
                'name': 'Sensor no loc_id (IP fallback)',
                'packet': '#Sensor:ADC1=500,ADC2=600!',
                'expected_type': 'sensor',
                'check': lambda p: p.get('loc_id') == '127.0.0.1' and p.get('ADC1') == 500
            }
        ]
        
        for tc in test_cases:
            received_packets.clear()
            server.handle_packet(tc['packet'], '127.0.0.1')
            if received_packets:
                packet = received_packets[0]
                passed = packet.get('type') == tc['expected_type'] and tc['check'](packet)
                log_test(f"Parse {tc['name']}", passed, 
                        None if passed else f"Got {packet}")
            else:
                log_test(f"Parse {tc['name']}", False, "No packet received")
                
    except Exception as e:
        log_test("TCP Packet Parsing", False, str(e))

def test_ip_loc_resolver():
    """Test IP to Location resolver"""
    print("\n=== Testing IP→Loc Resolver ===")
    
    try:
        from ip_loc_resolver import IPLocResolver
        
        # Create temp resolver
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_resolver.db')
            resolver = IPLocResolver(db_path=db_path)
            
            # Test set and get
            resolver.set_mapping('192.168.1.100', 'test room')
            loc = resolver.get_loc_id('192.168.1.100')
            log_test("Resolver set/get mapping", loc == 'test room', 
                    None if loc == 'test room' else f"Expected 'test room', got '{loc}'")
            
            # Test unknown IP
            loc = resolver.get_loc_id('192.168.1.200')
            log_test("Resolver unknown IP", loc is None,
                    None if loc is None else f"Expected None, got '{loc}'")
            
            # Test clear
            resolver.clear_mapping('192.168.1.100')
            loc = resolver.get_loc_id('192.168.1.100')
            log_test("Resolver clear mapping", loc is None,
                    None if loc is None else f"Expected None after clear, got '{loc}'")
            
            # Test persistence
            resolver.set_mapping('10.0.0.1', 'persistent room')
            resolver2 = IPLocResolver(db_path=db_path)
            loc = resolver2.get_loc_id('10.0.0.1')
            log_test("Resolver persistence", loc == 'persistent room',
                    None if loc == 'persistent room' else f"Expected 'persistent room', got '{loc}'")
            
            # Test import/export JSON
            test_mappings = {'10.1.1.1': 'room A', '10.1.1.2': 'room B'}
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_mappings, f)
                json_file = f.name
            
            try:
                resolver.import_json(json_file)
                loc_a = resolver.get_loc_id('10.1.1.1')
                loc_b = resolver.get_loc_id('10.1.1.2')
                log_test("Resolver import JSON", 
                        loc_a == 'room A' and loc_b == 'room B',
                        None if (loc_a == 'room A' and loc_b == 'room B') else f"Import failed")
                
                # Test export
                export_file = os.path.join(tmpdir, 'export.json')
                resolver.export_json(export_file)
                with open(export_file) as f:
                    exported = json.load(f)
                log_test("Resolver export JSON", 
                        '10.1.1.1' in exported and exported['10.1.1.1'] == 'room A',
                        None if '10.1.1.1' in exported else "Export incomplete")
            finally:
                os.unlink(json_file)
                
    except Exception as e:
        log_test("IP→Loc Resolver", False, str(e))

def test_pfds_manager():
    """Test PFDS device manager"""
    print("\n=== Testing PFDS Manager ===")
    
    try:
        from pfds_manager import PFDSManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_pfds.db')
            manager = PFDSManager(db_path=db_path)
            
            # Test add device
            success = manager.add_device('TestDevice', '192.168.1.50', 'lab', 'Test note')
            log_test("PFDS add device", success, None if success else "Add failed")
            
            # Test get devices
            devices = manager.get_devices()
            found = any(d['device_name'] == 'TestDevice' for d in devices)
            log_test("PFDS get devices", found, 
                    None if found else "Device not found in list")
            
            # Test update device
            if devices:
                dev_id = next(d['id'] for d in devices if d['device_name'] == 'TestDevice')
                success = manager.update_device(dev_id, 'UpdatedDevice', '192.168.1.51', 'lab2', 'Updated')
                log_test("PFDS update device", success, None if success else "Update failed")
            
            # Test delete device
            if devices:
                dev_id = next(d['id'] for d in devices if d['device_name'] in ['TestDevice', 'UpdatedDevice'])
                success = manager.delete_device(dev_id)
                log_test("PFDS delete device", success, None if success else "Delete failed")
                
    except Exception as e:
        log_test("PFDS Manager", False, str(e))

def test_tcp_logger():
    """Test TCP logging with rotation"""
    print("\n=== Testing TCP Logger ===")
    
    try:
        from tcp_logger import log_raw_packet, log_error_packet, get_tcp_log_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override log path
            import tcp_logger
            old_log_dir = tcp_logger.LOG_DIR
            tcp_logger.LOG_DIR = tmpdir
            
            try:
                # Log some packets
                log_raw_packet('#test:packet1!', 'room1')
                log_raw_packet('#test:packet2!', 'room2')
                log_error_packet('test error', 'bad packet', 'room3')
                
                # Check log file exists
                log_file = get_tcp_log_path()
                exists = os.path.exists(log_file)
                log_test("TCP logger creates log", exists,
                        None if exists else f"Log file not found: {log_file}")
                
                if exists:
                    with open(log_file) as f:
                        content = f.read()
                    has_raw = 'packet1' in content
                    has_error = 'test error' in content
                    log_test("TCP logger writes packets", has_raw and has_error,
                            None if (has_raw and has_error) else "Log content incomplete")
            finally:
                tcp_logger.LOG_DIR = old_log_dir
                
    except Exception as e:
        log_test("TCP Logger", False, str(e))

def test_database_manager():
    """Test database manager for user authentication"""
    print("\n=== Testing Database Manager ===")
    
    try:
        from database_manager import DatabaseManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_users.db')
            db = DatabaseManager(db_path)
            
            # Test create user
            success = db.create_user('testuser', 'testpass123', 'test@example.com', 'admin')
            log_test("DB create user", success, None if success else "Create user failed")
            
            # Test authenticate
            user = db.authenticate_user('testuser', 'testpass123')
            log_test("DB authenticate valid user", user is not None,
                    None if user else "Authentication failed for valid credentials")
            
            # Test wrong password
            user = db.authenticate_user('testuser', 'wrongpass')
            log_test("DB reject wrong password", user is None,
                    None if user is None else "Authentication succeeded with wrong password")
            
            # Test get users
            users = db.get_all_users()
            found = any(u[1] == 'testuser' for u in users)
            log_test("DB get all users", found,
                    None if found else "User not in list")
                    
    except Exception as e:
        log_test("Database Manager", False, str(e))

def test_stream_config():
    """Test stream configuration"""
    print("\n=== Testing Stream Config ===")
    
    try:
        # Test reading stream_config.json
        config_path = 'stream_config.json'
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = json.load(f)
            
            has_tcp_port = 'tcp_port' in config
            log_test("Stream config has tcp_port", has_tcp_port,
                    None if has_tcp_port else "tcp_port not in config")
            
            has_streams = 'streams' in config
            log_test("Stream config has streams", has_streams,
                    None if has_streams else "streams not in config")
        else:
            log_test("Stream config exists", False, f"File not found: {config_path}")
            
    except Exception as e:
        log_test("Stream Config", False, str(e))

def test_thermal_frame_parsing():
    """Test thermal frame parser with target temperature extraction"""
    print("\n=== Testing Thermal Frame Parsing ===")
    
    try:
        from thermal_frame_parser import ThermalFrameParser
        import numpy as np
        
        # Generate test frame with known temperatures
        test_grid_hex = ""
        for r in range(24):
            for c in range(32):
                # Create test pattern: room temp (25°C) with hot spot at center
                if 10 <= r <= 13 and 14 <= c <= 17:
                    # Hot spot at 60°C
                    temp_celsius = 60.0
                else:
                    # Room temp 25°C
                    temp_celsius = 25.0
                
                # Convert to raw value (centi-degrees offset from calibration)
                raw_delta = int((temp_celsius - 27.0) / 0.01)
                if raw_delta < 0:
                    raw_value = raw_delta + 0x10000
                else:
                    raw_value = raw_delta
                raw_value = max(0, min(0xFFFF, raw_value))
                test_grid_hex += f"{raw_value:04X}"
        
        # Add EEPROM (66 words = 264 chars)
        eeprom_hex = "03E8" + "FF9C" + ("0000" * 64)
        test_frame = test_grid_hex + eeprom_hex
        
        # Parse frame
        result = ThermalFrameParser.parse_frame(test_frame)
        grid = result['grid']
        
        # Test 1: Grid shape
        correct_shape = grid.shape == (24, 32)
        log_test("Thermal frame grid shape", correct_shape,
                None if correct_shape else f"Got shape {grid.shape}")
        
        # Test 2: Target temperature (max value)
        target_temp = grid.max()
        expected_target = 60.0
        target_correct = abs(target_temp - expected_target) < 1.0
        log_test("Target temperature extraction", target_correct,
                None if target_correct else f"Expected ~{expected_target}°C, got {target_temp:.2f}°C")
        
        # Test 3: Ambient temperature (min/mean of non-hot cells)
        ambient_temp = grid.min()
        expected_ambient = 25.0
        ambient_correct = abs(ambient_temp - expected_ambient) < 1.0
        log_test("Ambient temperature detection", ambient_correct,
                None if ambient_correct else f"Expected ~{expected_ambient}°C, got {ambient_temp:.2f}°C")
        
        # Test 4: Hot cells detection
        threshold = 50.0
        hot_cells = np.argwhere(grid >= threshold)
        has_hot_cells = len(hot_cells) > 0
        log_test("Hot cells detection", has_hot_cells,
                None if has_hot_cells else "No hot cells detected")
        
    except Exception as e:
        log_test("Thermal Frame Parsing", False, str(e))

def test_sensor_fusion_hot_cells():
    """Test sensor fusion hot cell identification"""
    print("\n=== Testing Sensor Fusion Hot Cells ===")
    
    try:
        from sensor_fusion import SensorFusion
        import numpy as np
        
        fusion = SensorFusion(temp_threshold=50.0)
        
        # Create test thermal matrix with known hot spots
        matrix = np.ones((24, 32)) * 25.0  # Room temp
        
        # Add hot spots
        matrix[10, 15] = 70.0  # Hot spot 1
        matrix[12, 20] = 65.0  # Hot spot 2
        matrix[15, 10] = 55.0  # Hot spot 3
        
        # Run fusion
        result = fusion.fuse(thermal_matrix=matrix.tolist())
        
        # Test 1: Alarm triggered
        log_test("Fusion triggers alarm on hot spots", result['alarm'],
                None if result['alarm'] else "Alarm not triggered")
        
        # Test 2: Hot cells identified
        hot_cells = result.get('hot_cells', [])
        expected_hot_cells = 3
        correct_count = len(hot_cells) == expected_hot_cells
        log_test("Fusion identifies hot cells", correct_count,
                None if correct_count else f"Expected {expected_hot_cells}, got {len(hot_cells)}")
        
        # Test 3: Thermal max reported
        thermal_max = result.get('thermal_max', 0)
        expected_max = 70.0
        max_correct = abs(thermal_max - expected_max) < 0.1
        log_test("Fusion reports thermal max", max_correct,
                None if max_correct else f"Expected {expected_max}, got {thermal_max}")
        
    except Exception as e:
        log_test("Sensor Fusion Hot Cells", False, str(e))

def test_integration_tcp_server():
    """Integration test: Start TCP server and send packets"""
    print("\n=== Integration Test: TCP Server ===")
    
    try:
        from tcp_sensor_server import TCPSensorServer
        import threading
        
        received = []
        
        def callback(packet):
            received.append(packet)
        
        server = TCPSensorServer(port=9002, packet_callback=callback)
        server.start()
        time.sleep(0.5)  # Let server start
        
        try:
            # Connect and send test packets
            sock = socket.socket()
            sock.connect(('127.0.0.1', 9002))
            
            # Send locid
            sock.sendall(b'#locid:integration test!\n')
            time.sleep(0.1)
            
            # Send sensor
            sock.sendall(b'#Sensor:integration test:ADC1=999!\n')
            time.sleep(0.1)
            
            sock.close()
            time.sleep(0.2)
            
            # Check received
            has_locid = any(p.get('type') == 'locid' for p in received)
            has_sensor = any(p.get('type') == 'sensor' and p.get('ADC1') == 999 for p in received)
            
            log_test("Integration: Server receives locid", has_locid,
                    None if has_locid else f"Received: {received}")
            log_test("Integration: Server receives sensor", has_sensor,
                    None if has_sensor else f"Received: {received}")
                    
        finally:
            server.stop()
            time.sleep(0.3)
            
    except Exception as e:
        log_test("Integration TCP Server", False, str(e))

def smoke_test():
    """Quick smoke test of core functionality"""
    print("\n=== Smoke Test ===")
    
    try:
        # Can we import key modules?
        modules = [
            'tcp_sensor_server',
            'ip_loc_resolver', 
            'pfds_manager',
            'tcp_logger',
            'database_manager'
        ]
        
        for mod in modules:
            try:
                __import__(mod)
                log_test(f"Import {mod}", True)
            except Exception as e:
                log_test(f"Import {mod}", False, str(e))
        
        # Check critical files exist
        files = [
            'main.py',
            'main_window.py',
            'EmberEye.spec',
            'requirements.txt',
            'stream_config.json'
        ]
        
        for file in files:
            exists = os.path.exists(file)
            log_test(f"File exists: {file}", exists,
                    None if exists else f"Missing {file}")
                    
    except Exception as e:
        log_test("Smoke Test", False, str(e))

def run_all_tests():
    """Run complete test suite"""
    print("=" * 60)
    print("EmberEye Comprehensive Test Suite")
    print("=" * 60)
    
    # Smoke tests first
    smoke_test()
    
    # Unit tests
    test_tcp_packet_parsing()
    test_ip_loc_resolver()
    test_pfds_manager()
    test_tcp_logger()
    test_database_manager()
    test_stream_config()
    test_thermal_frame_parsing()
    test_sensor_fusion_hot_cells()
    
    # Integration tests
    test_integration_tcp_server()
    
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
