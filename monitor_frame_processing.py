"""
Real-time Frame Processing Monitor
Monitors both detection systems to verify which one is actually processing frames
"""
import sys
import os
sys.path.insert(0, r'd:/EE/EmberEye')

import time
from embereye.core.detection_queue import get_detection_queue
from embereye.core.detection_worker import get_detection_worker

def monitor_detection_systems(duration_seconds=10):
    """
    Monitor both detection systems in real-time
    """
    print("=" * 80)
    print("REAL-TIME FRAME PROCESSING MONITOR")
    print("=" * 80)
    print(f"\nMonitoring for {duration_seconds} seconds...")
    print("This will show which detection system is actively processing frames.\n")
    
    # Get queue and worker
    queue = get_detection_queue()
    
    try:
        worker = get_detection_worker()
        worker_running = worker.is_running() if worker else False
    except:
        worker = None
        worker_running = False
    
    print(f"Detection Worker Status: {'RUNNING' if worker_running else 'NOT RUNNING'}")
    print(f"\nStarting monitor...")
    print("-" * 80)
    
    # Initial baseline
    initial_queue_stats = queue.get_stats()
    initial_worker_stats = worker.get_stats() if worker else None
    
    start_time = time.time()
    last_report = start_time
    
    while time.time() - start_time < duration_seconds:
        time.sleep(1)
        now = time.time()
        
        # Get current stats
        queue_stats = queue.get_stats()
        worker_stats = worker.get_stats() if worker else None
        
        # Calculate deltas since last report
        delta_queued = queue_stats['total_queued'] - initial_queue_stats['total_queued']
        delta_processed = queue_stats['total_processed'] - initial_queue_stats['total_processed']
        delta_dropped = queue_stats['total_dropped'] - initial_queue_stats['total_dropped']
        
        elapsed = now - start_time
        
        # Report
        print(f"\n[{elapsed:6.1f}s] Detection System Status:")
        print(f"  Hybrid Queue:")
        print(f"    Queued:    {delta_queued:5d} frames")
        print(f"    Processed: {delta_processed:5d} frames")
        print(f"    Dropped:   {delta_dropped:5d} frames")
        print(f"    Queue size: {queue_stats['queue_size']:4d}")
        
        if worker_stats:
            initial_worker = initial_worker_stats or {'frames_processed': 0, 'frames_dropped': 0}
            worker_delta_p = worker_stats['frames_processed'] - initial_worker.get('frames_processed', 0)
            worker_delta_d = worker_stats['frames_dropped'] - initial_worker.get('frames_dropped', 0)
            
            print(f"  Detection Worker:")
            print(f"    Processed: {worker_delta_p:5d} frames")
            print(f"    Dropped:   {worker_delta_d:5d} frames")
            print(f"    Avg latency: {worker_stats['avg_inference_ms']:6.1f}ms")
            print(f"    Model loaded: {worker_stats['model_loaded']}")
        
        # Analysis
        if delta_queued == 0 and elapsed > 3:
            print(f"\n  ⚠ WARNING: No frames queued to hybrid system!")
            print(f"     → Old ThreadPool system may be processing all frames")
            print(f"     → Hybrid system is BYPASSED")
        
        if delta_queued > 0 and delta_processed == 0 and elapsed > 3:
            print(f"\n  ⚠ WARNING: Frames queued but not processed!")
            print(f"     → Detection worker may not be running")
            print(f"     → Model may have failed to load")
        
        if delta_processed > 0:
            processing_rate = delta_processed / max(delta_queued, 1) * 100
            print(f"\n  ✓ Hybrid system processing: {processing_rate:.1f}%")
    
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    
    final_queue = queue.get_stats()
    final_worker = worker.get_stats() if worker else None
    
    total_queued = final_queue['total_queued'] - initial_queue_stats['total_queued']
    total_processed = final_queue['total_processed'] - initial_queue_stats['total_processed']
    total_dropped = final_queue['total_dropped'] - initial_queue_stats['total_dropped']
    
    print(f"\nHybrid Detection System ({duration_seconds}s):")
    print(f"  Frames queued:    {total_queued}")
    print(f"  Frames processed: {total_processed}")
    print(f"  Frames dropped:   {total_dropped}")
    
    if final_worker:
        worker_processed = final_worker['frames_processed'] - initial_worker_stats.get('frames_processed', 0)
        worker_dropped = final_worker['frames_dropped'] - initial_worker_stats.get('frames_dropped', 0)
        print(f"\nDetection Worker:")
        print(f"  Processed: {worker_processed}")
        print(f"  Dropped:   {worker_dropped}")
        print(f"  Model:     {'LOADED' if final_worker['model_loaded'] else 'NOT LOADED'}")
    
    print(f"\nConclusion:")
    if total_queued == 0:
        print("  ✗ Hybrid system NOT receiving frames")
        print("     Possible causes:")
        print("     • All frames have heuristic score < 0.20 (unlikely)")
        print("     • Hybrid detection code path not executing")  
        print("     • Old ThreadPool system is the only active path")
    elif total_processed == 0:
        print("  ✗ Hybrid system receiving frames but NOT processing")
        print("     Possible causes:")
        print("     • Detection worker not started")
        print("     • YOLO model failed to load")
        print("     • Worker thread crashed")
    elif total_processed < total_queued * 0.9:
        print(f"  ⚠ Hybrid system processing only {total_processed}/{total_queued} frames")
        print("     • Some frames timing out (> 1.5s age)")
        print("     • YOLO inference too slow")
    else:
        print("  ✓ Hybrid system working as expected")
        print(f"     Processing rate: {total_processed/max(total_queued,1)*100:.1f}%")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    try:
        print("\n" + "!" * 80)
        print("! NOTE: This monitor tracks the GLOBAL detection queue.")
        print("! To see actual activity, you need to:")
        print("!   1. Start EmberEye-Field application")
        print("!   2. Add at least one video stream")
        print("!   3. Let it run for a few seconds")
        print("!   4. Then run this monitor in parallel")
        print("!" * 80)
        print("\nPress Ctrl+C to exit anytime.\n")
        
        monitor_detection_systems(duration_seconds=15)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
