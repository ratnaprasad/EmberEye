#!/usr/bin/env python3
"""
Headless smoke test for EmberEye inference.
Tests model loading, inference, and detection sanity.
Can run in CI environments (CPU-only, no GUI).
"""

import sys
import time
import argparse
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_test_image(size=(640, 480)):
    """Create a synthetic test image for inference."""
    try:
        import numpy as np
        import cv2
        
        # Create image with some structure (gradient + shapes)
        img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        
        # Gradient background
        for i in range(size[1]):
            img[i, :] = [int(i / size[1] * 255), 128, 200 - int(i / size[1] * 200)]
        
        # Add some shapes (simulate objects)
        cv2.rectangle(img, (100, 100), (300, 300), (255, 0, 0), -1)
        cv2.circle(img, (size[0] // 2, size[1] // 2), 80, (0, 255, 0), -1)
        cv2.rectangle(img, (400, 150), (550, 400), (0, 0, 255), 3)
        
        # Add noise for realism
        noise = np.random.randint(0, 50, img.shape, dtype=np.uint8)
        img = cv2.add(img, noise)
        
        return img
    except ImportError:
        print("WARNING: cv2/numpy not available, using PIL fallback")
        from PIL import Image, ImageDraw
        img = Image.new('RGB', size, color=(128, 128, 200))
        draw = ImageDraw.Draw(img)
        draw.rectangle([100, 100, 300, 300], fill=(255, 0, 0))
        draw.ellipse([size[0]//2 - 80, size[1]//2 - 80, size[0]//2 + 80, size[1]//2 + 80], fill=(0, 255, 0))
        draw.rectangle([400, 150, 550, 400], outline=(0, 0, 255), width=3)
        return img


def run_smoke_test(model_path=None, skip_detection_check=False, verbose=False):
    """
    Run headless inference smoke test.
    
    Args:
        model_path: Path to model weights (default: current_best.pt)
        skip_detection_check: If True, don't fail on zero detections
        verbose: Print detailed output
    
    Returns:
        dict: Test results with keys (passed, fps, latency_ms, detections)
    """
    results = {
        'passed': False,
        'fps': 0.0,
        'latency_ms': 0,
        'detections': 0,
        'error': None
    }
    
    try:
        # Import dependencies
        try:
            from ultralytics import YOLO
        except ImportError:
            results['error'] = "ultralytics not installed (pip install ultralytics)"
            return results
        
        # Resolve model path
        if model_path is None:
            from embereye.core.model_versioning import ModelVersionManager
            manager = ModelVersionManager()
            current_best = manager.get_current_best()
            if current_best and current_best.exists():
                model_path = str(current_best)
            else:
                # Try base yolov8n as fallback
                model_path = "yolov8n.pt"
                if verbose:
                    print(f"No trained model found, using base {model_path}")
        
        model_path = Path(model_path)
        if not model_path.exists():
            results['error'] = f"Model not found: {model_path}"
            return results
        
        if verbose:
            print(f"Loading model: {model_path}")
        
        # Load model
        model = YOLO(str(model_path))
        
        if verbose:
            print(f"Model loaded successfully")
            print(f"Classes: {len(model.names)}")
        
        # Create test image
        test_img = create_test_image()
        
        # Warm-up inference (exclude from timing)
        if verbose:
            print("Running warm-up inference...")
        _ = model.predict(test_img, verbose=False, conf=0.25)
        
        # Timed inference (5 iterations for stability)
        if verbose:
            print("Running timed inference...")
        
        iterations = 5
        total_detections = 0
        start_time = time.time()
        
        for i in range(iterations):
            results_list = model.predict(test_img, verbose=False, conf=0.25, iou=0.45)
            if results_list and len(results_list) > 0:
                boxes = results_list[0].boxes
                if boxes is not None:
                    total_detections += len(boxes)
        
        elapsed = time.time() - start_time
        
        # Calculate metrics
        fps = iterations / elapsed if elapsed > 0 else 0
        latency_ms = int((elapsed / iterations) * 1000)
        avg_detections = total_detections / iterations
        
        results['fps'] = round(fps, 2)
        results['latency_ms'] = latency_ms
        results['detections'] = total_detections
        
        if verbose:
            print(f"\nResults:")
            print(f"  FPS: {results['fps']:.2f}")
            print(f"  Latency: {results['latency_ms']}ms")
            print(f"  Total detections: {total_detections} ({avg_detections:.1f} avg)")
        
        # Pass criteria
        if skip_detection_check:
            results['passed'] = True
            if verbose:
                print("\n✓ PASS (detection check skipped)")
        elif total_detections == 0:
            results['error'] = "Zero detections (model may be untrained)"
            if verbose:
                print(f"\n✗ FAIL: {results['error']}")
        else:
            results['passed'] = True
            if verbose:
                print("\n✓ PASS")
        
        return results
    
    except Exception as e:
        results['error'] = str(e)
        if verbose:
            import traceback
            print(f"\n✗ FAIL: {e}")
            traceback.print_exc()
        return results


def main():
    parser = argparse.ArgumentParser(description="EmberEye headless smoke test")
    parser.add_argument('--model', type=str, help="Path to model weights")
    parser.add_argument('--skip-detection-check', action='store_true',
                       help="Don't fail on zero detections (useful for base models)")
    parser.add_argument('--verbose', '-v', action='store_true',
                       help="Print detailed output")
    
    args = parser.parse_args()
    
    if args.verbose:
        print("=" * 60)
        print("EmberEye Headless Smoke Test")
        print("=" * 60)
    
    results = run_smoke_test(
        model_path=args.model,
        skip_detection_check=args.skip_detection_check,
        verbose=args.verbose
    )
    
    # Exit with appropriate code
    if results['passed']:
        if args.verbose:
            print("\n✓ Smoke test passed")
        sys.exit(0)
    else:
        if not args.verbose:
            print(f"✗ Smoke test failed: {results['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
