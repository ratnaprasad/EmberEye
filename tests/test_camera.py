import cv2
import sys

print("OpenCV version:", cv2.__version__)
print("\nTesting camera backends:")

for idx in [0, 1]:
    print(f"\n--- Testing device index {idx} ---")
    for name in ['CAP_ANY', 'CAP_AVFOUNDATION']:
        if not hasattr(cv2, name):
            continue
        code = getattr(cv2, name)
        try:
            if name == 'CAP_ANY':
                cap = cv2.VideoCapture(idx)
            else:
                cap = cv2.VideoCapture(idx, code)
            
            is_open = cap.isOpened()
            print(f"{name}: opened={is_open}", end="")
            
            if is_open:
                ret, frame = cap.read()
                print(f", read={ret}", end="")
                if ret and frame is not None:
                    print(f", shape={frame.shape}")
                else:
                    print(", frame=None")
            else:
                print()
            
            cap.release()
        except Exception as e:
            print(f"{name}: ERROR - {e}")
