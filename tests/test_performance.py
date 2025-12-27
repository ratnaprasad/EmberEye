#!/usr/bin/env python3
"""
Performance and Load Testing
Tests frame throughput, memory usage, reconnection speed.
"""
import sys
import os
import time
import psutil
import gc
from pathlib import Path

test_results = []

def log_perf_test(name, value, unit, threshold=None, status=None):
    """Log performance test result."""
    if status is None and threshold is not None:
        status = "PASS" if value <= threshold else "FAIL"
    elif status is None:
        status = "INFO"
    
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "ℹ️"
    result = {
        "name": name,
        "value": value,
        "unit": unit,
        "threshold": threshold,
        "status": status
    }
    test_results.append(result)
    
    threshold_str = f" (threshold: {threshold}{unit})" if threshold else ""
    print(f"{icon} {name}: {value:.2f}{unit}{threshold_str} - {status}")
    return status == "PASS" or status == "INFO"

def test_frame_parsing_performance():
    """Test 1: Frame parsing throughput."""
    print("\n=== Test 1: Frame Parsing Performance ===")
    
    try:
        from thermal_frame_parser import ThermalFrameParser
        import numpy as np
        
        # Generate realistic test frame (3336 chars: grid + EEPROM)
        test_frame = "".join([f"{(i*17 + 137) % 65536:04X}" for i in range(834)])
        
        # Warm-up
        for _ in range(10):
            try:
                ThermalFrameParser.parse_frame(test_frame)
            except:
                pass
        
        # Benchmark
        iterations = 1000
        start = time.time()
        successful = 0
        
        for _ in range(iterations):
            try:
                parsed = ThermalFrameParser.parse_frame(test_frame)
                if parsed and 'grid' in parsed:
                    successful += 1
            except Exception as e:
                pass
        
        elapsed = time.time() - start
        fps = successful / elapsed
        avg_ms = (elapsed / successful) * 1000 if successful > 0 else 0
        
        log_perf_test("Parse throughput", fps, " fps", threshold=30)
        log_perf_test("Parse latency", avg_ms, " ms", threshold=33.3)
        log_perf_test("Parse success rate", (successful/iterations)*100, "%", threshold=95)
        
        return fps >= 30
        
    except Exception as e:
        log_perf_test("Frame parsing", 0, " fps", status="FAIL")
        print(f"Error: {e}")
        return False

def test_memory_usage():
    """Test 2: Memory usage under load."""
    print("\n=== Test 2: Memory Usage ===")
    
    try:
        process = psutil.Process(os.getpid())
        
        # Baseline memory
        gc.collect()
        baseline_mb = process.memory_info().rss / 1024 / 1024
        log_perf_test("Baseline memory", baseline_mb, " MB", status="INFO")
        
        # Simulate frame processing load
        from thermal_frame_parser import ThermalFrameParser
        frames_cache = []
        
        test_frame = "".join([f"{(i*17) % 65536:04X}" for i in range(834)])
        
        for i in range(100):
            try:
                parsed = ThermalFrameParser.parse_frame(test_frame)
                if parsed and 'grid' in parsed:
                    frames_cache.append(parsed['grid'])
            except:
                pass
        
        # Measure after load
        loaded_mb = process.memory_info().rss / 1024 / 1024
        delta_mb = loaded_mb - baseline_mb
        
        log_perf_test("Memory after 100 frames", loaded_mb, " MB", status="INFO")
        log_perf_test("Memory increase", delta_mb, " MB", threshold=50)
        
        # Clear and measure cleanup
        frames_cache.clear()
        gc.collect()
        
        after_gc_mb = process.memory_info().rss / 1024 / 1024
        recovered_mb = loaded_mb - after_gc_mb
        
        log_perf_test("Memory recovered after GC", recovered_mb, " MB", status="INFO")
        
        return delta_mb < 50
        
    except Exception as e:
        log_perf_test("Memory usage", 0, " MB", status="FAIL")
        print(f"Error: {e}")
        return False

def test_eeprom_validation_performance():
    """Test 3: EEPROM validation speed."""
    print("\n=== Test 3: EEPROM Validation Performance ===")
    
    try:
        from thermal_frame_parser import ThermalFrameParser
        
        # Valid EEPROM (66 blocks = 264 chars)
        valid_eeprom = "".join([f"{i*13 % 65536:04X}" for i in range(66)])
        
        # Invalid EEPROMs
        invalid_eeprom_short = "1234" * 50  # Too short
        invalid_eeprom_zeros = "0000" * 66  # All zeros
        
        # Benchmark validation
        iterations = 10000
        
        start = time.time()
        for _ in range(iterations):
            ThermalFrameParser.is_eeprom_valid(valid_eeprom)
        elapsed = time.time() - start
        
        validations_per_sec = iterations / elapsed
        avg_us = (elapsed / iterations) * 1_000_000
        
        log_perf_test("EEPROM validation throughput", validations_per_sec, " validations/sec", status="INFO")
        log_perf_test("EEPROM validation latency", avg_us, " μs", threshold=100)
        
        # Test accuracy
        valid_result = ThermalFrameParser.is_eeprom_valid(valid_eeprom)
        invalid_short_result = ThermalFrameParser.is_eeprom_valid(invalid_eeprom_short)
        invalid_zeros_result = ThermalFrameParser.is_eeprom_valid(invalid_eeprom_zeros)
        
        accuracy = (valid_result and not invalid_short_result and not invalid_zeros_result)
        log_perf_test("EEPROM validation accuracy", 100 if accuracy else 0, "%", threshold=95)
        
        return avg_us < 100
        
    except Exception as e:
        log_perf_test("EEPROM validation", 0, " validations/sec", status="FAIL")
        print(f"Error: {e}")
        return False

def test_tcp_packet_parsing():
    """Test 4: TCP packet parsing speed."""
    print("\n=== Test 4: TCP Packet Parsing ===")
    
    try:
        # Simulate packet parsing (without actual TCP connection)
        test_packets = [
            "#serialno:SIM123456!\n",
            "#locid:cam01!\n",
            "#frame1:" + ("1234" * 834) + "!\n",
            "#Sensor:cam01:ADC1=1500,ADC2=2000,MPY30=1!\n"
        ]
        
        iterations = 1000
        start = time.time()
        
        for _ in range(iterations):
            for packet in test_packets:
                # Simulate parsing logic
                if packet.startswith('#serialno:'):
                    serial = packet.split(':', 1)[1].rstrip('!\n').strip()
                elif packet.startswith('#locid:'):
                    loc_id = packet.split(':', 1)[1].rstrip('!\n').strip()
                elif packet.startswith('#frame'):
                    content = packet[1:].rstrip('!\n')
                    if ':' in content:
                        prefix, data = content.split(':', 1)
                elif packet.startswith('#Sensor'):
                    content = packet[1:].rstrip('!\n')
                    if ':' in content:
                        parts = content.split(':', 2)
        
        elapsed = time.time() - start
        packets_per_sec = (iterations * len(test_packets)) / elapsed
        avg_us = (elapsed / (iterations * len(test_packets))) * 1_000_000
        
        log_perf_test("Packet parsing throughput", packets_per_sec, " packets/sec", threshold=1000)
        log_perf_test("Packet parsing latency", avg_us, " μs", threshold=1000)
        
        return packets_per_sec >= 1000
        
    except Exception as e:
        log_perf_test("TCP packet parsing", 0, " packets/sec", status="FAIL")
        print(f"Error: {e}")
        return False

def test_concurrent_frame_processing():
    """Test 5: Concurrent frame processing (simulated multi-camera)."""
    print("\n=== Test 5: Concurrent Processing ===")
    
    try:
        from thermal_frame_parser import ThermalFrameParser
        import threading
        
        test_frame = "".join([f"{(i*17) % 65536:04X}" for i in range(834)])
        
        results = {"count": 0, "lock": threading.Lock()}
        
        def process_frames(camera_id, num_frames):
            for _ in range(num_frames):
                try:
                    parsed = ThermalFrameParser.parse_frame(test_frame)
                    if parsed and 'grid' in parsed:
                        with results["lock"]:
                            results["count"] += 1
                except:
                    pass
        
        # Simulate 4 cameras processing 100 frames each
        num_cameras = 4
        frames_per_camera = 100
        
        start = time.time()
        threads = []
        
        for i in range(num_cameras):
            thread = threading.Thread(target=process_frames, args=(i, frames_per_camera))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        elapsed = time.time() - start
        total_frames = num_cameras * frames_per_camera
        fps = results["count"] / elapsed
        
        log_perf_test(f"Concurrent processing ({num_cameras} cameras)", fps, " fps", threshold=60)
        log_perf_test("Frame success rate", (results["count"]/total_frames)*100, "%", threshold=95)
        
        return fps >= 60
        
    except Exception as e:
        log_perf_test("Concurrent processing", 0, " fps", status="FAIL")
        print(f"Error: {e}")
        return False

def generate_report():
    """Generate performance report."""
    print("\n" + "="*60)
    print("PERFORMANCE TEST SUMMARY")
    print("="*60)
    
    total = len([r for r in test_results if r["status"] in ["PASS", "FAIL"]])
    passed = sum(1 for r in test_results if r["status"] == "PASS")
    failed = sum(1 for r in test_results if r["status"] == "FAIL")
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"\nSuccess Rate: {passed/total*100:.1f}%")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if r["status"] == "FAIL":
                threshold = f" (threshold: {r['threshold']}{r['unit']})" if r['threshold'] else ""
                print(f"  - {r['name']}: {r['value']:.2f}{r['unit']}{threshold}")
    
    # Save report
    import json
    os.makedirs("logs", exist_ok=True)
    with open("logs/performance_report.json", "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {"total": total, "passed": passed, "failed": failed},
            "results": test_results
        }, f, indent=2)
    
    print(f"\n📄 Report saved to: logs/performance_report.json")
    
    return failed == 0

def main():
    """Run all performance tests."""
    print("="*60)
    print("EMBERYE PERFORMANCE TESTS")
    print("="*60)
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"CPU: {psutil.cpu_count()} cores")
    print(f"Memory: {psutil.virtual_memory().total / 1024 / 1024 / 1024:.1f} GB")
    
    tests = [
        test_frame_parsing_performance,
        test_memory_usage,
        test_eeprom_validation_performance,
        test_tcp_packet_parsing,
        test_concurrent_frame_processing
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            log_perf_test(test_func.__name__, 0, "", status="FAIL")
            print(f"Error: {e}")
    
    success = generate_report()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
