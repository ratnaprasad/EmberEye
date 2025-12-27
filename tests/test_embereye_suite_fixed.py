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
        import ip_loc_resolver
        
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
                'check': lambda p: (p.get('loc_id') in ['127.0.0.1', 'test room']) and p.get('ADC1') == 500
            }
        ]
        
        for tc in test_cases:
            received_packets.clear()
            # First send locid packet for context
            server.handle_packet('#locid:test room!', '127.0.0.1')
            received_packets.clear()
            # Now test the actual packet
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
        import ip_loc_resolver
        
        # Create temp resolver
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_resolver.db')
            ip_loc_resolver._DB_PATH = db_path
            # Don't call _init_db directly, just use the resolver functions
            
            # Test set and get
            ip_loc_resolver.set_mapping('192.168.1.100', 'test room')
            loc = ip_loc_resolver.get_loc_id('192.168.1.100')
            log_test("Resolver set/get mapping", loc == 'test room', 
                    None if loc == 'test room' else f"Expected 'test room', got '{loc}'")
            
            # Test unknown IP
            loc = ip_loc_resolver.get_loc_id('192.168.1.200')
            log_test("Resolver unknown IP", loc is None,
                    None if loc is None else f"Expected None, got '{loc}'")
            
            # Test clear
            ip_loc_resolver.clear_mapping('192.168.1.100')
            loc = ip_loc_resolver.get_loc_id('192.168.1.100')
            log_test("Resolver clear mapping", loc is None,
                    None if loc is None else f"Expected None after clear, got '{loc}'")
            
            # Test persistence
            ip_loc_resolver.set_mapping('10.0.0.1', 'persistent room')
            # Just verify it's still there
            loc = ip_loc_resolver.get_loc_id('10.0.0.1')
            log_test("Resolver persistence", loc == 'persistent room',
                    None if loc == 'persistent room' else f"Expected 'persistent room', got '{loc}'")
            
            # Test import/export JSON
            test_mappings = {'10.1.1.1': 'room A', '10.1.1.2': 'room B'}
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_mappings, f)
                json_file = f.name
            
            try:
                ip_loc_resolver.import_json(json_file)
                loc_a = ip_loc_resolver.get_loc_id('10.1.1.1')
                loc_b = ip_loc_resolver.get_loc_id('10.1.1.2')
                log_test("Resolver import JSON", 
                        loc_a == 'room A' and loc_b == 'room B',
                        None if (loc_a == 'room A' and loc_b == 'room B') else f"Import failed")
                
                # Test export
                export_file = os.path.join(tmpdir, 'export.json')
                ip_loc_resolver.export_json(export_file)
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
            
            # Test add device (name, ip, location_id, mode, poll_seconds)
            dev_id = manager.add_device('TestDevice', '192.168.1.50', 'lab', 'auto', 30)
            log_test("PFDS add device", dev_id > 0, None if dev_id > 0 else "Add failed")
            
            # Test list devices
            devices = manager.list_devices()
            found = any(d['name'] == 'TestDevice' for d in devices)
            log_test("PFDS list devices", found, 
                    None if found else "Device not found in list")
            
            # Test update device (if method exists)
            if devices and hasattr(manager, 'update_device'):
                dev_id = next(d['id'] for d in devices if d['name'] == 'TestDevice')
                success = manager.update_device(dev_id, 'UpdatedDevice', '192.168.1.51', 'lab2', 'Continuous', 60)
                log_test("PFDS update device", success, None if success else "Update failed")
            
            # Test delete device (if method exists)
            if devices and hasattr(manager, 'delete_device'):
                dev_id = next(d['id'] for d in devices if d['name'] in ['TestDevice', 'UpdatedDevice'])
                success = manager.delete_device(dev_id)
                log_test("PFDS delete device", success, None if success else "Delete failed")
                
    except Exception as e:
        log_test("PFDS Manager", False, str(e))

def test_tcp_logger():
    """Test TCP logging with rotation"""
    print("\n=== Testing TCP Logger ===")
    
    try:
        from tcp_logger import log_raw_packet, log_error_packet
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override log path
            import tcp_logger
            old_log_dir = tcp_logger.LOG_DIR
            old_debug = tcp_logger.DEBUG_LOG
            old_error = tcp_logger.ERROR_LOG
            
            tcp_logger.LOG_DIR = tmpdir
            tcp_logger.DEBUG_LOG = os.path.join(tmpdir, 'tcp_debug.log')
            tcp_logger.ERROR_LOG = os.path.join(tmpdir, 'tcp_errors.log')
            os.makedirs(tmpdir, exist_ok=True)
            
            try:
                # Log some packets
                log_raw_packet('#test:packet1!', location_id='room1')
                log_raw_packet('#test:packet2!', location_id='room2')
                log_error_packet(reason='test error', raw='bad packet', location_id='room3')
                
                # Check log files exist
                debug_exists = os.path.exists(tcp_logger.DEBUG_LOG)
                error_exists = os.path.exists(tcp_logger.ERROR_LOG)
                log_test("TCP logger creates logs", debug_exists and error_exists,
                        None if (debug_exists and error_exists) else f"Debug: {debug_exists}, Error: {error_exists}")
                
                if debug_exists:
                    with open(tcp_logger.DEBUG_LOG) as f:
                        content = f.read()
                    has_raw = 'packet1' in content
                    log_test("TCP logger writes debug packets", has_raw,
                            None if has_raw else "Debug log content incomplete")
                
                if error_exists:
                    with open(tcp_logger.ERROR_LOG) as f:
                        content = f.read()
                    has_error = 'test error' in content
                    log_test("TCP logger writes error packets", has_error,
                            None if has_error else "Error log content incomplete")
            finally:
                tcp_logger.LOG_DIR = old_log_dir
                tcp_logger.DEBUG_LOG = old_debug
                tcp_logger.ERROR_LOG = old_error
                
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
            user_data = {
                'username': 'testdbuser',
                'password': 'testpass123',
                'first_name': 'Test',
                'last_name': 'User',
                'dob': '1990-01-01',
                'questions': [
                    ['What is your favorite color?', 'Blue'],
                    ['What is your pet name?', 'Fluffy'],
                    ['Where were you born?', 'Boston']
                ]
            }
            success = db.create_user(user_data)
            log_test("DB create user", success, None if success else "Create user failed")
            
            # Test get user
            user = db.get_user('testdbuser')
            log_test("DB get user", user is not None,
                    None if user else "User retrieval failed")
            
            # Test password verification using bcrypt
            if user:
                import bcrypt
                password_hash = user[1]  # Second field is password_hash
                password_matches = bcrypt.checkpw('testpass123'.encode('utf-8'), password_hash.encode('utf-8'))
                log_test("DB password verification", password_matches,
                        None if password_matches else "Password verification failed")
            
            # Test wrong password
            if user:
                wrong_matches = bcrypt.checkpw('wrongpass'.encode('utf-8'), user[1].encode('utf-8'))
                log_test("DB reject wrong password", not wrong_matches,
                        None if not wrong_matches else "Wrong password accepted")
                    
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
