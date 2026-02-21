"""
Hybrid Detection Frame Processing Verification
Checks if all frames are being processed by the hybrid detection system
"""
import sys
import os
sys.path.insert(0, r'd:/EE/EmberEye')

import time
from embereye.core.detection_queue import get_detection_queue
from embereye.core.detection_worker import get_detection_worker, stop_detection_worker
from embereye.core.hybrid_detector import HybridDetector
import numpy as np
import cv2

def create_test_frame(fire_pixels_ratio=0.3):
    """Create a synthetic frame with simulated fire colors"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Add some fire-colored pixels (orange/red)
    h, w = frame.shape[:2]
    fire_area = int(h * w * fire_pixels_ratio)
    
    # Convert to HSV to set fire colors
    hsv = np.zeros((480, 640, 3), dtype=np.uint8)
    # Fire: Hue 0-40 (orange/red), Saturation 100-255, Value 100-255
    hsv[:, :, 0] = np.random.randint(0, 40, (h, w)).astype(np.uint8)  # Hue
    hsv[:, :, 1] = np.random.randint(100, 255, (h, w)).astype(np.uint8)  # Saturation
    hsv[:, :, 2] = np.random.randint(100, 255, (h, w)).astype(np.uint8)  # Value
    
    # Convert back to BGR
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return frame

def verify_frame_processing():
    """Verify that frames are being processed by hybrid detector"""
    print("=" * 70)
    print("HYBRID DETECTION FRAME PROCESSING VERIFICATION")
    print("=" * 70)
    
    # Create hybrid detector
    detector = HybridDetector(model_path=None, stream_id="test-stream")
    queue = get_detection_queue()
    
    # Get initial stats
    initial_stats = queue.get_stats()
    print(f"\n[INITIAL STATE]")
    print(f"  Queue size: {initial_stats['queue_size']}")
    print(f"  Total queued: {initial_stats['total_queued']}")
    print(f"  Total processed: {initial_stats['total_processed']}")
    print(f"  Total dropped: {initial_stats['total_dropped']}")
    print(f"  Queue overflow: {initial_stats['queue_overflow']}")
    
    # Test 1: Heuristic filtering
    print(f"\n{'='*70}")
    print("[TEST 1] Heuristic Filtering")
    print("Testing frames with different fire/smoke characteristics...")
    
    test_cases = [
        ("Low fire content", 0.01),
        ("Moderate fire content", 0.15),
        ("High fire content", 0.30),
        ("Very high fire content", 0.50),
    ]
    
    heuristic_results = []
    for desc, fire_ratio in test_cases:
        frame = create_test_frame(fire_ratio)
        h_score = detector.heuristic_detect(frame)
        heuristic_results.append((desc, fire_ratio, h_score))
        queued = h_score >= detector.heuristic_threshold
        status = "✓ QUEUED" if queued else "✗ FILTERED"
        print(f"  {desc:30s} | Fire ratio: {fire_ratio:.2f} | Heuristic: {h_score:.3f} | {status}")
    
    # Test 2: Frame queueing
    print(f"\n{'='*70}")
    print("[TEST 2] Frame Queueing")
    print("Submitting suspicious frames to queue...")
    
    frames_submitted = 0
    frames_queued = 0
    
    for i in range(10):
        # Create frames with varying fire content
        fire_ratio = 0.1 + (i * 0.05)  # 0.1 to 0.55
        frame = create_test_frame(fire_ratio)
        h_score, result = detector.detect_frame(frame)
        
        if h_score >= detector.heuristic_threshold:
            frames_submitted += 1
            print(f"  Frame {i+1:2d}: heuristic={h_score:.3f} → QUEUED")
        else:
            print(f"  Frame {i+1:2d}: heuristic={h_score:.3f} → FILTERED")
    
    # Check queue status
    mid_stats = queue.get_stats()
    frames_queued = mid_stats['total_queued'] - initial_stats['total_queued']
    
    print(f"\n  Frames submitted: {frames_submitted}")
    print(f"  Frames queued: {frames_queued}")
    print(f"  Queue size now: {mid_stats['queue_size']}")
    
    # Test 3: Check if worker is running
    print(f"\n{'='*70}")
    print("[TEST 3] Detection Worker Status")
    
    try:
        # Try to get detection worker (may not be running)
        worker = get_detection_worker()
        if worker and worker.is_running():
            print(f"  ✓ Detection worker is RUNNING")
            worker_stats = worker.get_stats()
            print(f"  Frames processed: {worker_stats['frames_processed']}")
            print(f"  Frames dropped: {worker_stats['frames_dropped']}")
            print(f"  Avg inference time: {worker_stats['avg_inference_ms']:.1f}ms")
            print(f"  Model loaded: {worker_stats['model_loaded']}")
            print(f"  Queue depth: {worker_stats['queue_size']}")
        else:
            print(f"  ✗ Detection worker is NOT RUNNING")
            print(f"  → Frames are QUEUED but NOT PROCESSED")
    except Exception as e:
        print(f"  ✗ Detection worker ERROR: {e}")
    
    # Test 4: Wait for processing
    print(f"\n{'='*70}")
    print("[TEST 4] Frame Processing Wait Test")
    print("Waiting 5 seconds for worker to process queued frames...")
    
    time.sleep(5)
    
    final_stats = queue.get_stats()
    frames_processed = final_stats['total_processed'] - initial_stats['total_processed']
    
    print(f"\n  Frames queued in this test: {frames_queued}")
    print(f"  Frames processed in this test: {frames_processed}")
    print(f"  Queue size remaining: {final_stats['queue_size']}")
    
    if frames_processed > 0:
        print(f"\n  ✓ WORKER IS PROCESSING FRAMES")
        processing_rate = (frames_processed / frames_queued * 100) if frames_queued > 0 else 0
        print(f"  Processing rate: {processing_rate:.1f}%")
    else:
        print(f"\n  ✗ WORKER IS NOT PROCESSING FRAMES")
        print(f"  → Frames remain in queue without being processed")
    
    # Final summary
    print(f"\n{'='*70}")
    print("[SUMMARY]")
    print("=" * 70)
    
    print(f"\n1. Heuristic Filtering:")
    print(f"   - Threshold: {detector.heuristic_threshold}")
    queued_count = sum(1 for _, _, h in heuristic_results if h >= detector.heuristic_threshold)
    print(f"   - Frames above threshold: {queued_count}/{len(heuristic_results)}")
    
    print(f"\n2. Queue Management:")
    print(f"   - Total queued: {final_stats['total_queued']}")
    print(f"   - Total processed: {final_stats['total_processed']}")
    print(f"   - Total dropped: {final_stats['total_dropped']}")
    print(f"   - Current queue size: {final_stats['queue_size']}")
    
    print(f"\n3. Frame Processing:")
    if frames_processed > 0:
        print(f"   ✓ Hybrid model IS processing frames")
        print(f"   - Frames queued in test: {frames_queued}")
        print(f"   - Frames processed in test: {frames_processed}")
    else:
        print(f"   ✗ Hybrid model IS NOT processing frames")
        print(f"   - Possible issues:")
        print(f"     • Detection worker not started")
        print(f"     • Model not loaded")
        print(f"     • Worker thread crashed")
    
    print(f"\n4. Recommendations:")
    if frames_processed == 0 and frames_queued > 0:
        print(f"   • Start detection worker in main_window.py")
        print(f"   • Verify model path in HybridDetector")
        print(f"   • Check worker thread logs for errors")
    elif frames_processed < frames_queued:
        print(f"   • Some frames are being dropped (age > 1.5s)")
        print(f"   • Consider increasing worker threads")
        print(f"   • Or reduce queue max age threshold")
    else:
        print(f"   • System is working as expected")
    
    print(f"\n{'='*70}")

if __name__ == "__main__":
    try:
        verify_frame_processing()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            stop_detection_worker()
        except:
            pass
