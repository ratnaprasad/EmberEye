"""Test if VisionDetector is using imported model or heuristic-only."""
import sys
sys.path.insert(0, '..')
from embereye.core.vision_detector import VisionDetector
import numpy as np
import cv2

# Test 
v = VisionDetector()
print('=' * 60)
print('MODEL STATUS:')
print(f'  Model Path: {v.yolo_model_path}')
print(f'  Model Loaded: {v.model_loaded}')
print(f'  Using YOLO: {"YES" if v.model_loaded else "NO (heuristic only)"}')
print('=' * 60)

# Create a test frame with fire-like colors
frame = np.zeros((480, 640, 3), dtype=np.uint8)
# Fill with orange/red colors (simulating fire)
frame[:, :] = [20, 100, 255]  # BGR: Orange color

# Convert to HSV and check
hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
print('\nTEST FRAME (Fire-colored):')
print(f'  BGR color: [20, 100, 255] (orange)')
print(f'  HSV: H={hsv[0,0,0]}, S={hsv[0,0,1]}, V={hsv[0,0,2]}')

# Run detection
h_score = v.heuristic_fire_smoke(frame)
y_score = v.yolo_detect(frame)
final = v.detect(frame)

print('\nDETECTION RESULTS:')
print(f'  Heuristic Score: {h_score:.3f}')
print(f'  YOLO Score: {y_score:.3f}')
print(f'  Final Score: {final:.3f}')

print('\nCONCLUSION:')
if not v.model_loaded:
    print('  ⚠ YOLO model NOT loaded - using HEURISTIC ONLY')
    print('  ⚠ Imported model in ./models is NOT being used')
    print('  ✓ Detection still works via color-based heuristic')
else:
    print('  ✓ YOLO model loaded and active')
print('=' * 60)

# Test if we can manually load the imported model
print('\nATTEMPT TO LOAD IMPORTED MODEL:')
import glob
models = glob.glob('models/*.pt')
if models:
    print(f'  Found models: {models}')
    if v.load_model(models[0]):
        print('  ✓ Successfully loaded imported model!')
        # Re-test
        y_score2 = v.yolo_detect(frame)
        print(f'  YOLO Score after load: {y_score2:.3f}')
    else:
        print('  ✗ Failed to load model')
else:
    print('  ✗ No models found in ./models')
