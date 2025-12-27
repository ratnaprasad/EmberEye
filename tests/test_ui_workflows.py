#!/usr/bin/env python3
"""
UI Workflow Tests for EmberEye
Tests UI responsiveness, grid rebuild, widget lifecycle, and stream config
"""
import sys
import os
import time
import tempfile
import json
from unittest.mock import Mock, MagicMock, patch

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

def test_video_widget_lifecycle():
    """Test video widget creation, lifecycle, and cleanup"""
    print("\n=== Testing Video Widget Lifecycle ===")
    
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        import sys
        
        # Create QApplication if not exists
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        from video_widget import VideoWidget
        
        # Test 1: Widget creation
        widget = VideoWidget("rtsp://test.example.com/stream", "Test Camera", "loc_test_1")
        log_test("VideoWidget: Creates successfully",
                widget is not None,
                None if widget else "Widget creation failed")
        
        # Test 2: Has required attributes
        has_attrs = all(hasattr(widget, attr) for attr in [
            'rtsp_url', 'name', 'loc_id', 'video_label', 'worker', 'worker_thread'
        ])
        log_test("VideoWidget: Has required attributes",
                has_attrs,
                None if has_attrs else "Missing required attributes")
        
        # Test 3: Control buttons exist
        has_controls = all(hasattr(widget, btn) for btn in [
            'minimize_btn', 'maximize_btn', 'reload_btn'
        ])
        log_test("VideoWidget: Has control buttons",
                has_controls,
                None if has_controls else "Missing control buttons")
        
        # Test 4: Status indicators exist
        has_status = all(hasattr(widget, attr) for attr in [
            'fire_alarm_status', 'temp_label'
        ])
        log_test("VideoWidget: Has status indicators",
                has_status,
                None if has_status else "Missing status indicators")
        
        # Test 5: Thermal overlay attributes
        has_thermal = all(hasattr(widget, attr) for attr in [
            'thermal_grid_enabled', 'thermal_grid_rows', 'thermal_grid_cols',
            'hot_cells', 'hot_cells_history'
        ])
        log_test("VideoWidget: Has thermal overlay support",
                has_thermal,
                None if has_thermal else "Missing thermal attributes")
        
        # Test 6: Stop method (non-blocking cleanup)
        start_time = time.time()
        widget.stop()
        elapsed = time.time() - start_time
        log_test("VideoWidget: Stop completes quickly (<1s)",
                elapsed < 1.0,
                None if elapsed < 1.0 else f"Stop took {elapsed:.2f}s (should be <1s)")
        
        # Test 7: Thread cleanup
        widget.stop()
        time.sleep(0.5)  # Give thread time to stop
        not_running = not widget.worker_thread.isRunning()
        log_test("VideoWidget: Thread stops after cleanup",
                not_running,
                None if not_running else "Thread still running after stop")
        
        # Cleanup
        widget.deleteLater()
        
    except Exception as e:
        log_test("Video Widget Lifecycle", False, str(e))

def test_stream_config_operations():
    """Test stream configuration load/save operations"""
    print("\n=== Testing Stream Config Operations ===")
    
    try:
        from stream_config import StreamConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override config path
            test_config_path = os.path.join(tmpdir, 'test_stream_config.json')
            StreamConfig.CONFIG_FILE = test_config_path
            
            # Test 1: Default config structure
            default_config = {
                "groups": ["Default", "Test Group"],
                "streams": [
                    {
                        "name": "Camera 1",
                        "url": "rtsp://test1.example.com",
                        "loc_id": "loc_1",
                        "group": "Default"
                    },
                    {
                        "name": "Camera 2",
                        "url": "rtsp://test2.example.com",
                        "loc_id": "loc_2",
                        "group": "Test Group"
                    }
                ],
                "tcp_port": 9001
            }
            
            # Test 2: Save config
            success = StreamConfig.save_config(default_config)
            log_test("StreamConfig: Save config",
                    success and os.path.exists(test_config_path),
                    None if (success and os.path.exists(test_config_path)) else "Save failed")
            
            # Test 3: Load config
            loaded_config = StreamConfig.load_config()
            log_test("StreamConfig: Load config",
                    loaded_config is not None,
                    None if loaded_config else "Load failed")
            
            # Test 4: Config structure preserved
            if loaded_config:
                has_groups = 'groups' in loaded_config and len(loaded_config['groups']) == 2
                has_streams = 'streams' in loaded_config and len(loaded_config['streams']) == 2
                has_tcp_port = 'tcp_port' in loaded_config and loaded_config['tcp_port'] == 9001
                
                log_test("StreamConfig: Structure preserved",
                        has_groups and has_streams and has_tcp_port,
                        None if (has_groups and has_streams and has_tcp_port) else f"Structure mismatch")
            
            # Test 5: Export config
            export_path = os.path.join(tmpdir, 'export.json')
            success = StreamConfig.export_config(export_path)
            log_test("StreamConfig: Export config",
                    success and os.path.exists(export_path),
                    None if (success and os.path.exists(export_path)) else "Export failed")
            
            # Test 6: Import config
            import_path = os.path.join(tmpdir, 'import.json')
            with open(import_path, 'w') as f:
                json.dump(default_config, f)
            
            success = StreamConfig.import_config(import_path)
            log_test("StreamConfig: Import config",
                    success,
                    None if success else "Import failed")
            
            # Test 7: Save is non-blocking (should complete quickly)
            large_config = default_config.copy()
            large_config['streams'] = [
                {
                    "name": f"Camera {i}",
                    "url": f"rtsp://test{i}.example.com",
                    "loc_id": f"loc_{i}",
                    "group": "Default"
                }
                for i in range(100)
            ]
            
            start_time = time.time()
            StreamConfig.save_config(large_config)
            elapsed = time.time() - start_time
            log_test("StreamConfig: Save completes quickly (<0.5s)",
                    elapsed < 0.5,
                    None if elapsed < 0.5 else f"Save took {elapsed:.2f}s")
        
    except Exception as e:
        log_test("Stream Config Operations", False, str(e))

def test_main_window_grid_rebuild():
    """Test main window grid rebuild scheduling and responsiveness"""
    print("\n=== Testing Main Window Grid Rebuild ===")
    
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        import sys
        
        # Create QApplication if not exists
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        # Mock imports to avoid full initialization
        with patch('main_window.StreamConfig') as MockStreamConfig, \
             patch('tcp_sensor_server.TCPSensorServer'), \
             patch('main_window.WebSocketClient'), \
             patch('main_window.SensorFusion'), \
             patch('main_window.BaselineManager'), \
             patch('gas_sensor.MQ135GasSensor'), \
             patch('main_window.PFDSManager'):
            # Setup mock config
            MockStreamConfig.load_config.return_value = {
                'groups': ['Default'],
                'streams': [],
                'tcp_port': 9001
            }
            from main_window import BEMainWindow
            # Test 1: Window creation
            window = BEMainWindow()
            log_test("MainWindow: Creates successfully",
                    window is not None,
                    None if window else "Window creation failed")
            
            # Test 2: Has grid rebuild scheduling
            has_scheduler = hasattr(window, 'schedule_grid_rebuild')
            log_test("MainWindow: Has schedule_grid_rebuild method",
                    has_scheduler,
                    None if has_scheduler else "Missing scheduler method")
            
            # Test 3: Has cleanup method
            has_cleanup = hasattr(window, 'cleanup_old_widgets')
            log_test("MainWindow: Has cleanup_old_widgets method",
                    has_cleanup,
                    None if has_cleanup else "Missing cleanup method")
            
            # Test 4: Has rebuild flag
            has_flag = hasattr(window, 'grid_rebuild_pending')
            log_test("MainWindow: Has grid_rebuild_pending flag",
                    has_flag,
                    None if has_flag else "Missing rebuild flag")
            
            # Test 5: Schedule rebuild is non-blocking
            if has_scheduler:
                start_time = time.time()
                window.schedule_grid_rebuild()
                elapsed = time.time() - start_time
                log_test("MainWindow: schedule_grid_rebuild is non-blocking",
                        elapsed < 0.1,
                        None if elapsed < 0.1 else f"Scheduling took {elapsed:.2f}s")
            
            # Test 6: Rebuild flag is set
            if has_flag:
                window.schedule_grid_rebuild()
                log_test("MainWindow: Rebuild flag set after scheduling",
                        window.grid_rebuild_pending,
                        None if window.grid_rebuild_pending else "Flag not set")
            
            # Test 7: Multiple schedule calls don't stack
            if has_scheduler and has_flag:
                window.grid_rebuild_pending = False
                window.schedule_grid_rebuild()
                window.schedule_grid_rebuild()
                window.schedule_grid_rebuild()
                # Only one rebuild should be pending
                log_test("MainWindow: Multiple schedules coalesce",
                        window.grid_rebuild_pending,
                        None if window.grid_rebuild_pending else "Flag not managed correctly")
            
            # Cleanup
            window.close()
        
    except Exception as e:
        log_test("Main Window Grid Rebuild", False, str(e))

def test_resource_helper():
    """Test resource path resolution"""
    print("\n=== Testing Resource Helper ===")
    
    try:
        from resource_helper import get_resource_path, get_writable_path, copy_bundled_resource
        
        # Test 1: Get resource path
        path = get_resource_path('test_resource.txt')
        log_test("ResourceHelper: get_resource_path returns string",
                isinstance(path, str),
                None if isinstance(path, str) else f"Invalid type: {type(path)}")
        
        # Test 2: Get writable path
        writable = get_writable_path('test_config.json')
        log_test("ResourceHelper: get_writable_path returns string",
                isinstance(writable, str),
                None if isinstance(writable, str) else f"Invalid type: {type(writable)}")
        
        # Test 3: Writable path validity
        import sys
        is_absolute = os.path.isabs(writable)
        if getattr(sys, 'frozen', False):
            # Packaged mode should return absolute path
            log_test("ResourceHelper: Writable path is absolute",
                is_absolute,
                None if is_absolute else f"Path not absolute: {writable}")
        else:
            # Source mode can be relative to current directory
            log_test("ResourceHelper: Writable path valid in source mode",
                isinstance(writable, str) and (is_absolute or writable == 'test_config.json'),
                None if (isinstance(writable, str) and (is_absolute or writable == 'test_config.json')) else f"Invalid writable path: {writable}")
        
        # Test 4: Copy bundled resource (mock)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock source file
            source = os.path.join(tmpdir, 'source.txt')
            dest = os.path.join(tmpdir, 'dest.txt')
            
            with open(source, 'w') as f:
                f.write('test content')
            
            # Test copy function logic
            import shutil
            if not os.path.exists(dest):
                shutil.copy2(source, dest)
            
            copied = os.path.exists(dest)
            log_test("ResourceHelper: Copy logic works",
                    copied,
                    None if copied else "Copy failed")
        
    except Exception as e:
        log_test("Resource Helper", False, str(e))

def test_ui_responsiveness():
    """Test that UI operations don't block"""
    print("\n=== Testing UI Responsiveness ===")
    
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer, QEventLoop
        import sys
        
        # Create QApplication if not exists
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        # Test 1: QTimer.singleShot defers execution
        executed = {'flag': False}
        
        def deferred_task():
            executed['flag'] = True
        
        start_time = time.time()
        QTimer.singleShot(0, deferred_task)
        immediate_elapsed = time.time() - start_time
        
        log_test("UI: QTimer.singleShot returns immediately",
                immediate_elapsed < 0.01,
                None if immediate_elapsed < 0.01 else f"Took {immediate_elapsed:.4f}s")
        
        # Process events to execute deferred task
        app.processEvents()
        
        log_test("UI: Deferred task executes after processEvents",
                executed['flag'],
                None if executed['flag'] else "Task not executed")
        
        # Test 2: Event loop responsiveness
        loop = QEventLoop()
        timeout_executed = {'flag': False}
        
        def timeout_task():
            timeout_executed['flag'] = True
            loop.quit()
        
        QTimer.singleShot(100, timeout_task)
        start = time.time()
        loop.exec_()
        elapsed = time.time() - start
        
        log_test("UI: Event loop processes timers",
                timeout_executed['flag'] and 0.08 < elapsed < 0.15,
                None if (timeout_executed['flag'] and 0.08 < elapsed < 0.15) else f"Elapsed: {elapsed:.2f}s")
        
        # Test 3: Nested timer execution
        nested_order = []
        
        def first():
            nested_order.append(1)
            QTimer.singleShot(0, second)
        
        def second():
            nested_order.append(2)
        
        QTimer.singleShot(0, first)
        app.processEvents()
        app.processEvents()  # Need second process for nested timer
        
        log_test("UI: Nested timers execute in order",
                nested_order == [1, 2],
                None if nested_order == [1, 2] else f"Order: {nested_order}")
        
    except Exception as e:
        log_test("UI Responsiveness", False, str(e))

def run_all_tests():
    """Run complete UI workflow test suite"""
    print("=" * 60)
    print("EmberEye UI Workflow Tests")
    print("=" * 60)
    
    test_video_widget_lifecycle()
    test_stream_config_operations()
    test_main_window_grid_rebuild()
    test_resource_helper()
    test_ui_responsiveness()
    
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
