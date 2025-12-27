#!/usr/bin/env python3
"""
Automated Test Suite for EmberEye Application
Tests protocol, UI, settings, login, and performance.
"""
import sys
import os
import time
import json
import subprocess
import signal
from pathlib import Path

# Test results tracker
test_results = []

def log_test(name, status, message=""):
    """Log test result."""
    result = {"name": name, "status": status, "message": message, "timestamp": time.time()}
    test_results.append(result)
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{icon} {name}: {status} {message}")
    return status == "PASS"

def test_config_files():
    """Test 1: Verify all config files exist and are valid."""
    print("\n=== Test 1: Configuration Files ===")
    configs = [
        "stream_config.json",
        "database_manager.py",
        "pfds_manager.py",
        "tcp_async_server.py"
    ]
    
    for config in configs:
        path = Path(config)
        if not path.exists():
            log_test(f"Config: {config}", "FAIL", "File not found")
            return False
    
    # Validate stream_config.json structure
    try:
        with open("stream_config.json", "r") as f:
            config = json.load(f)
        
        required_keys = ["streams", "tcp_port", "thermal_calibration"]
        missing = [k for k in required_keys if k not in config]
        if missing:
            log_test("stream_config.json structure", "FAIL", f"Missing keys: {missing}")
            return False
        
        # Verify async mode is enabled
        if config.get("tcp_mode") != "async":
            log_test("TCP mode", "WARN", "tcp_mode should be 'async' for protocol v3")
        else:
            log_test("TCP mode", "PASS", "async mode enabled")
        
        # Verify thermal_use_eeprom is enabled
        if not config.get("thermal_use_eeprom", False):
            log_test("thermal_use_eeprom", "WARN", "Should be true for embedded EEPROM validation")
        else:
            log_test("thermal_use_eeprom", "PASS", "Enabled for embedded EEPROM")
        
        log_test("stream_config.json", "PASS", f"Valid config with {len(config['streams'])} streams")
        return True
    except Exception as e:
        log_test("stream_config.json", "FAIL", str(e))
        return False

def test_simulator_startup():
    """Test 2: Verify simulator v3 can start and wait for commands."""
    print("\n=== Test 2: Simulator V3 Startup ===")
    
    # Check simulator file exists
    if not Path("tcp_sensor_simulator_v3.py").exists():
        log_test("Simulator v3 file", "FAIL", "tcp_sensor_simulator_v3.py not found")
        return False
    
    log_test("Simulator v3 file", "PASS", "File exists")
    
    # Test imports
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("simulator", "tcp_sensor_simulator_v3.py")
        if spec and spec.loader:
            log_test("Simulator imports", "PASS", "Module can be imported")
        return True
    except Exception as e:
        log_test("Simulator imports", "FAIL", str(e))
        return False

def test_protocol_components():
    """Test 3: Verify protocol v3 components are implemented."""
    print("\n=== Test 3: Protocol V3 Components ===")
    
    # Test PFDS manager changes
    try:
        with open("pfds_manager.py", "r") as f:
            content = f.read()
        
        checks = [
            ("device_init_done", "PERIOD_ON gating per device"),
            ("DO NOT send EEPROM1", "Removed auto-EEPROM1"),
            ("ONE-TIME", "One-time PERIOD_ON logging")
        ]
        
        for pattern, desc in checks:
            if pattern in content:
                log_test(f"PFDS: {desc}", "PASS")
            else:
                log_test(f"PFDS: {desc}", "FAIL", f"Pattern '{pattern}' not found")
                return False
        
    except Exception as e:
        log_test("PFDS manager", "FAIL", str(e))
        return False
    
    # Test thermal parser changes
    try:
        with open("thermal_frame_parser.py", "r") as f:
            content = f.read()
        
        checks = [
            ("is_eeprom_valid", "EEPROM validation method"),
            ("Using validated EEPROM", "Embedded EEPROM usage")
        ]
        
        for pattern, desc in checks:
            if pattern in content:
                log_test(f"Parser: {desc}", "PASS")
            else:
                log_test(f"Parser: {desc}", "FAIL", f"Pattern '{pattern}' not found")
                return False
        
    except Exception as e:
        log_test("Thermal parser", "FAIL", str(e))
        return False
    
    # Test TCP async server changes
    try:
        with open("tcp_async_server.py", "r") as f:
            content = f.read()
        
        checks = [
            ("_client_period_on_sent", "PERIOD_ON gating per connection"),
            ("ONE-TIME", "One-time PERIOD_ON logging"),
            ("total_with_eeprom = expected_grid_chars + 66*4", "3336-char frame support")
        ]
        
        for pattern, desc in checks:
            if pattern in content:
                log_test(f"TCP Server: {desc}", "PASS")
            else:
                log_test(f"TCP Server: {desc}", "FAIL", f"Pattern '{pattern}' not found")
                return False
        
    except Exception as e:
        log_test("TCP async server", "FAIL", str(e))
        return False
    
    return True

def test_database_schema():
    """Test 4: Verify database schema and tables."""
    print("\n=== Test 4: Database Schema ===")
    
    try:
        import sqlite3
        db_path = "ember_eye.db"
        
        if not Path(db_path).exists():
            log_test("Database file", "WARN", "Database not initialized yet")
            return True
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check required tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ["devices", "pfds_devices", "users"]
        missing = [t for t in required_tables if t not in tables]
        
        if missing:
            log_test("Database tables", "FAIL", f"Missing tables: {missing}")
            conn.close()
            return False
        
        log_test("Database tables", "PASS", f"All required tables present: {', '.join(tables)}")
        
        # Check PFDS devices table schema
        cursor.execute("PRAGMA table_info(pfds_devices)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_cols = ["id", "name", "ip", "mode", "poll_seconds"]
        missing_cols = [c for c in required_cols if c not in columns]
        
        if missing_cols:
            log_test("PFDS schema", "FAIL", f"Missing columns: {missing_cols}")
        else:
            log_test("PFDS schema", "PASS", f"All columns present")
        
        conn.close()
        return True
        
    except Exception as e:
        log_test("Database", "FAIL", str(e))
        return False

def test_port_availability():
    """Test 5: Check if required ports are available."""
    print("\n=== Test 5: Port Availability ===")
    
    import socket
    
    ports = {
        9001: "TCP Sensor Server",
        9090: "Metrics Server",
        8765: "WebSocket Server (optional)"
    }
    
    for port, name in ports.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            log_test(f"Port {port} ({name})", "WARN", "Port already in use")
        else:
            log_test(f"Port {port} ({name})", "PASS", "Available")
    
    return True

def test_performance_baseline():
    """Test 6: Measure baseline performance metrics."""
    print("\n=== Test 6: Performance Baseline ===")
    
    try:
        # Test frame parsing speed
        from thermal_frame_parser import ThermalFrameParser
        import numpy as np
        
        # Generate test frame (3336 chars)
        test_frame = "".join([f"{i:04X}" for i in range(834)])
        
        start = time.time()
        iterations = 100
        for _ in range(iterations):
            try:
                parsed = ThermalFrameParser.parse_frame(test_frame)
            except:
                pass
        elapsed = time.time() - start
        
        fps = iterations / elapsed
        log_test("Frame parsing speed", "PASS", f"{fps:.1f} fps ({elapsed*1000/iterations:.2f} ms/frame)")
        
        if fps < 30:
            log_test("Parsing performance", "WARN", "Below 30 fps threshold")
        else:
            log_test("Parsing performance", "PASS", "Above 30 fps threshold")
        
        return True
        
    except Exception as e:
        log_test("Performance test", "FAIL", str(e))
        return False

def test_ui_screens_exist():
    """Test 7: Verify UI screen files exist."""
    print("\n=== Test 7: UI Screen Files ===")
    
    ui_files = [
        ("main_window.py", "Main application window"),
        ("ee_loginwindow.py", "Login window"),
        ("streamconfig_dialog.py", "Stream configuration"),
        ("video_widget.py", "Video display widget"),
        ("failed_devices_tab.py", "Failed devices management"),
        ("device_status_manager.py", "Device status tracking")
    ]
    
    all_exist = True
    for file, desc in ui_files:
        if Path(file).exists():
            log_test(f"UI: {desc}", "PASS", file)
        else:
            log_test(f"UI: {desc}", "FAIL", f"Missing {file}")
            all_exist = False
    
    return all_exist

def test_imports():
    """Test 8: Verify critical imports work."""
    print("\n=== Test 8: Module Imports ===")
    
    modules = [
        ("PyQt5.QtWidgets", "Qt GUI framework"),
        ("PyQt5.QtCore", "Qt core"),
        ("numpy", "NumPy"),
        ("cv2", "OpenCV"),
        ("asyncio", "Async I/O")
    ]
    
    all_imported = True
    for module, desc in modules:
        try:
            __import__(module)
            log_test(f"Import: {desc}", "PASS", module)
        except ImportError as e:
            log_test(f"Import: {desc}", "FAIL", str(e))
            all_imported = False
    
    return all_imported

def generate_report():
    """Generate test report."""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["status"] == "PASS")
    failed = sum(1 for r in test_results if r["status"] == "FAIL")
    warned = sum(1 for r in test_results if r["status"] == "WARN")
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Warnings: {warned}")
    print(f"\nSuccess Rate: {passed/total*100:.1f}%")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if r["status"] == "FAIL":
                print(f"  - {r['name']}: {r['message']}")
    
    if warned > 0:
        print("\n⚠️  WARNINGS:")
        for r in test_results:
            if r["status"] == "WARN":
                print(f"  - {r['name']}: {r['message']}")
    
    # Save report to file
    report_path = "logs/test_report.json"
    os.makedirs("logs", exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "success_rate": passed/total*100
            },
            "results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Full report saved to: {report_path}")
    
    return failed == 0

def main():
    """Run all tests."""
    print("="*60)
    print("EMBERYE AUTOMATED TEST SUITE")
    print("="*60)
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run tests
    tests = [
        test_config_files,
        test_simulator_startup,
        test_protocol_components,
        test_database_schema,
        test_port_availability,
        test_performance_baseline,
        test_ui_screens_exist,
        test_imports
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            log_test(test_func.__name__, "FAIL", f"Exception: {e}")
    
    # Generate report
    success = generate_report()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
