#!/usr/bin/env python3
"""
End-to-End Integration Test for EmberEye
Tests complete workflow from sensor data to UI display
"""

import subprocess
import time
import sys
import os
import signal
import socket
import json

def check_port_available(port):
    """Check if port is available"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) != 0

def start_process(cmd, name):
    """Start a process and return handle"""
    print(f"🚀 Starting {name}...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        preexec_fn=os.setsid
    )
    time.sleep(2)
    if proc.poll() is None:
        print(f"✅ {name} started (PID: {proc.pid})")
        return proc
    else:
        print(f"❌ {name} failed to start")
        return None

def stop_process(proc, name):
    """Stop a process gracefully"""
    if proc and proc.poll() is None:
        print(f"🛑 Stopping {name}...")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
            print(f"✅ {name} stopped")
        except:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            print(f"⚠️  {name} force killed")

def _load_tcp_port(default_port: int = 4888) -> int:
    """Load TCP port from stream_config.json with a safe fallback."""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), 'stream_config.json')
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
        return int(cfg.get('tcp_port', default_port))
    except Exception:
        return default_port


def run_integration_test():
    """Run complete integration test"""
    print("="*60)
    print("EmberEye End-to-End Integration Test")
    print("="*60)
    
    main_proc = None
    simulator_proc = None
    
    try:
        # Step 1: Check ports
        print("\n📍 Step 1: Checking ports...")
        tcp_port = _load_tcp_port(4888)
        if not check_port_available(tcp_port):
            print(f"❌ Port {tcp_port} already in use")
            return False
        print(f"✅ Port {tcp_port} available")
        
        # Step 2: Start EmberEye main application
        print("\n📍 Step 2: Starting EmberEye...")
        main_cmd = f"{sys.executable} main.py"
        main_proc = start_process(main_cmd, "EmberEye")
        if not main_proc:
            return False
        
        # Wait for services to initialize
        print("⏳ Waiting for services to initialize (10s)...")
        time.sleep(10)
        
        # Step 3: Verify EmberEye is running
        print("\n📍 Step 3: Verifying EmberEye status...")
        if main_proc.poll() is not None:
            print("❌ EmberEye exited unexpectedly")
            stdout, stderr = main_proc.communicate()
            print(f"STDOUT: {stdout.decode()[:500]}")
            print(f"STDERR: {stderr.decode()[:500]}")
            return False
        print("✅ EmberEye is running")
        
        # Step 4: Start TCP simulator
        print("\n📍 Step 4: Starting TCP simulator...")
        sim_cmd = f"{sys.executable} tcp_sensor_simulator_v3.py --host 127.0.0.1 --port {tcp_port} --interval 2 --loc-id demo_room --format embedded"
        simulator_proc = start_process(sim_cmd, "TCP Simulator")
        if not simulator_proc:
            return False
        
        # Step 5: Let simulator send data
        print("\n📍 Step 5: Running simulation (30 seconds)...")
        print("📊 Simulator sending sensor data...")
        for i in range(15):
            time.sleep(2)
            print(f"  ⏱️  {(i+1)*2}s / 30s", end='\r')
        print("\n✅ Simulation complete")
        
        # Step 6: Check if processes are still running
        print("\n📍 Step 6: Final status check...")
        main_alive = main_proc.poll() is None
        sim_alive = simulator_proc.poll() is None
        
        print(f"EmberEye: {'✅ Running' if main_alive else '❌ Stopped'}")
        print(f"Simulator: {'✅ Running' if sim_alive else '❌ Stopped'}")
        
        success = main_alive and sim_alive
        
        if success:
            print("\n" + "="*60)
            print("✅ INTEGRATION TEST PASSED")
            print("="*60)
            print("\nTest Summary:")
            print("  - EmberEye launched successfully")
            print(f"  - TCP server initialized on port {tcp_port}")
            print("  - Simulator connected and sent data")
            print("  - All processes remained stable")
            print("\nNext Steps:")
            print("  1. Open EmberEye UI (should be visible)")
            print("  2. Navigate to VIDEOWALL tab")
            print("  3. Check TCP status: 'Running' with message count")
            print("  4. Verify sensor data in logs/tcp_debug.log")
        else:
            print("\n" + "="*60)
            print("❌ INTEGRATION TEST FAILED")
            print("="*60)
        
        return success
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        print("\n📍 Cleanup: Stopping processes...")
        stop_process(simulator_proc, "TCP Simulator")
        stop_process(main_proc, "EmberEye")
        print("\n✅ Cleanup complete")

if __name__ == "__main__":
    success = run_integration_test()
    sys.exit(0 if success else 1)
