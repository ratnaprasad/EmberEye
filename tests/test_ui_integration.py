#!/usr/bin/env python3
"""
UI Integration Test
Tests login, settings screens, and UI interactions automatically.
"""
import sys
import os
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtTest import QTest

# Test results
test_log = []

def log_ui_test(name, status, message=""):
    """Log UI test result."""
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    line = f"{icon} {name}: {status} {message}"
    print(line)
    test_log.append({"name": name, "status": status, "message": message})
    return status == "PASS"

class UITestRunner:
    """Automated UI test runner."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.login_window = None
    
    def test_login_window(self):
        """Test 1: Login window initialization."""
        print("\n=== Test 1: Login Window ===")
        
        try:
            from ee_loginwindow import EELoginWindow
            self.login_window = EELoginWindow()
            
            # Check window components
            if hasattr(self.login_window, 'username_input'):
                log_ui_test("Login: username field", "PASS")
            else:
                log_ui_test("Login: username field", "FAIL", "Field not found")
                return False
            
            if hasattr(self.login_window, 'password_input'):
                log_ui_test("Login: password field", "PASS")
            else:
                log_ui_test("Login: password field", "FAIL", "Field not found")
                return False
            
            if hasattr(self.login_window, 'login_button'):
                log_ui_test("Login: login button", "PASS")
            else:
                log_ui_test("Login: login button", "FAIL", "Button not found")
                return False
            
            log_ui_test("Login window initialization", "PASS", "All components present")
            return True
            
        except Exception as e:
            log_ui_test("Login window initialization", "FAIL", str(e))
            return False
    
    def test_auto_login(self):
        """Test 2: Automatic login with default credentials."""
        print("\n=== Test 2: Auto Login ===")
        
        try:
            if not self.login_window:
                log_ui_test("Auto login", "FAIL", "Login window not initialized")
                return False
            
            # Set credentials
            username_field = getattr(self.login_window, 'username_input', None)
            password_field = getattr(self.login_window, 'password_input', None)
            
            if username_field and password_field:
                username_field.setText("admin")
                password_field.setText("admin")
                log_ui_test("Set credentials", "PASS", "admin/admin")
            else:
                log_ui_test("Set credentials", "FAIL", "Input fields not accessible")
                return False
            
            # Simulate login button click
            login_btn = getattr(self.login_window, 'login_button', None)
            if login_btn:
                QTest.mouseClick(login_btn, Qt.LeftButton)
                log_ui_test("Login button click", "PASS")
                
                # Wait for main window
                QTest.qWait(1000)
                
                return True
            else:
                log_ui_test("Login button click", "FAIL", "Button not found")
                return False
                
        except Exception as e:
            log_ui_test("Auto login", "FAIL", str(e))
            return False
    
    def test_main_window_init(self):
        """Test 3: Main window initialization."""
        print("\n=== Test 3: Main Window ===")
        
        try:
            from main_window import BEMainWindow
            self.main_window = BEMainWindow()
            
            # Check main components
            if hasattr(self.main_window, 'tab_widget'):
                log_ui_test("Main: tab widget", "PASS")
            else:
                log_ui_test("Main: tab widget", "FAIL", "Tab widget not found")
                return False
            
            if hasattr(self.main_window, 'tcp_server'):
                log_ui_test("Main: TCP server", "PASS")
            else:
                log_ui_test("Main: TCP server", "WARN", "TCP server not initialized yet")
            
            if hasattr(self.main_window, 'pfds'):
                log_ui_test("Main: PFDS manager", "PASS")
            else:
                log_ui_test("Main: PFDS manager", "FAIL", "PFDS not initialized")
                return False
            
            if hasattr(self.main_window, 'device_status_manager'):
                log_ui_test("Main: Device status manager", "PASS")
            else:
                log_ui_test("Main: Device status manager", "FAIL", "Status manager not initialized")
                return False
            
            log_ui_test("Main window initialization", "PASS", "All managers present")
            return True
            
        except Exception as e:
            log_ui_test("Main window initialization", "FAIL", str(e))
            return False
    
    def test_stream_config_dialog(self):
        """Test 4: Stream configuration dialog."""
        print("\n=== Test 4: Stream Config Dialog ===")
        
        try:
            from streamconfig_dialog import StreamConfigDialog
            dialog = StreamConfigDialog()
            
            # Check dialog components
            if hasattr(dialog, 'stream_list'):
                log_ui_test("StreamConfig: stream list", "PASS")
            else:
                log_ui_test("StreamConfig: stream list", "FAIL")
                return False
            
            if hasattr(dialog, 'add_stream_button'):
                log_ui_test("StreamConfig: add button", "PASS")
            else:
                log_ui_test("StreamConfig: add button", "FAIL")
                return False
            
            log_ui_test("Stream config dialog", "PASS", "All components present")
            return True
            
        except Exception as e:
            log_ui_test("Stream config dialog", "FAIL", str(e))
            return False
    
    def test_video_widget(self):
        """Test 5: Video widget initialization."""
        print("\n=== Test 5: Video Widget ===")
        
        try:
            from video_widget import VideoWidget
            widget = VideoWidget("test_cam", "Test Camera", "0")
            
            # Check widget components
            if hasattr(widget, 'update_frame'):
                log_ui_test("VideoWidget: update_frame method", "PASS")
            else:
                log_ui_test("VideoWidget: update_frame method", "FAIL")
                return False
            
            if hasattr(widget, 'overlay_thermal'):
                log_ui_test("VideoWidget: thermal overlay", "PASS")
            else:
                log_ui_test("VideoWidget: thermal overlay", "WARN", "Method not found")
            
            log_ui_test("Video widget", "PASS", "Basic structure valid")
            return True
            
        except Exception as e:
            log_ui_test("Video widget", "FAIL", str(e))
            return False
    
    def test_failed_devices_tab(self):
        """Test 6: Failed devices tab."""
        print("\n=== Test 6: Failed Devices Tab ===")
        
        try:
            from failed_devices_tab import FailedDevicesTab
            from device_status_manager import DeviceStatusManager
            
            manager = DeviceStatusManager()
            tab = FailedDevicesTab(manager)
            
            # Check tab components
            if hasattr(tab, 'device_table'):
                log_ui_test("FailedDevices: device table", "PASS")
            else:
                log_ui_test("FailedDevices: device table", "FAIL")
                return False
            
            if hasattr(tab, 'reconnect_all_btn'):
                log_ui_test("FailedDevices: reconnect all button", "PASS")
            else:
                log_ui_test("FailedDevices: reconnect all button", "WARN", "Button not found")
            
            log_ui_test("Failed devices tab", "PASS", "Tab initialized correctly")
            return True
            
        except Exception as e:
            log_ui_test("Failed devices tab", "FAIL", str(e))
            return False
    
    def test_pfds_device_operations(self):
        """Test 7: PFDS device operations."""
        print("\n=== Test 7: PFDS Operations ===")
        
        try:
            from pfds_manager import PFDSManager, is_valid_ip
            
            pfds = PFDSManager()
            
            # Test IP validation
            valid_ips = ["192.168.1.1", "127.0.0.1", "10.0.0.1"]
            invalid_ips = ["999.999.999.999", "abc.def.ghi.jkl", "192.168.1"]
            
            for ip in valid_ips:
                if is_valid_ip(ip):
                    log_ui_test(f"IP validation: {ip}", "PASS")
                else:
                    log_ui_test(f"IP validation: {ip}", "FAIL", "Should be valid")
                    return False
            
            for ip in invalid_ips:
                if not is_valid_ip(ip):
                    log_ui_test(f"IP validation: {ip}", "PASS", "Correctly rejected")
                else:
                    log_ui_test(f"IP validation: {ip}", "FAIL", "Should be invalid")
                    return False
            
            # Test device addition
            test_device = {
                "name": "Test Device",
                "ip": "192.168.1.100",
                "mode": "Continuous",
                "poll_seconds": 5
            }
            
            device_id = pfds.add_device(**test_device)
            if device_id:
                log_ui_test("PFDS: add device", "PASS", f"Device ID: {device_id}")
                
                # Test device retrieval
                devices = pfds.list_devices()
                found = any(d["id"] == device_id for d in devices)
                if found:
                    log_ui_test("PFDS: list devices", "PASS")
                else:
                    log_ui_test("PFDS: list devices", "FAIL", "Device not found")
                    return False
                
                # Test device deletion
                pfds.delete_device(device_id)
                devices_after = pfds.list_devices()
                still_exists = any(d["id"] == device_id for d in devices_after)
                if not still_exists:
                    log_ui_test("PFDS: delete device", "PASS")
                else:
                    log_ui_test("PFDS: delete device", "FAIL", "Device still exists")
                    return False
            else:
                log_ui_test("PFDS: add device", "FAIL", "Failed to add device")
                return False
            
            return True
            
        except Exception as e:
            log_ui_test("PFDS operations", "FAIL", str(e))
            return False
    
    def run_all_tests(self):
        """Run all UI tests."""
        print("="*60)
        print("EMBERYE UI INTEGRATION TESTS")
        print("="*60)
        
        tests = [
            self.test_login_window,
            self.test_main_window_init,
            self.test_stream_config_dialog,
            self.test_video_widget,
            self.test_failed_devices_tab,
            self.test_pfds_device_operations
        ]
        
        for test_func in tests:
            try:
                test_func()
            except Exception as e:
                log_ui_test(test_func.__name__, "FAIL", f"Exception: {e}")
        
        self.generate_report()
    
    def generate_report(self):
        """Generate test report."""
        print("\n" + "="*60)
        print("UI TEST SUMMARY")
        print("="*60)
        
        total = len(test_log)
        passed = sum(1 for r in test_log if r["status"] == "PASS")
        failed = sum(1 for r in test_log if r["status"] == "FAIL")
        warned = sum(1 for r in test_log if r["status"] == "WARN")
        
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warned}")
        print(f"\nSuccess Rate: {passed/total*100:.1f}%")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for r in test_log:
                if r["status"] == "FAIL":
                    print(f"  - {r['name']}: {r['message']}")
        
        # Save report
        import json
        os.makedirs("logs", exist_ok=True)
        with open("logs/ui_test_report.json", "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "summary": {"total": total, "passed": passed, "failed": failed, "warned": warned},
                "results": test_log
            }, f, indent=2)
        
        print(f"\n📄 Report saved to: logs/ui_test_report.json")

def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    runner = UITestRunner()
    runner.app = app
    
    # Schedule tests to run after event loop starts
    QTimer.singleShot(100, runner.run_all_tests)
    QTimer.singleShot(5000, app.quit)  # Auto-quit after 5 seconds
    
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
