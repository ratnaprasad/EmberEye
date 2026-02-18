"""
Test Hybrid Detection Algorithm on Video File
Processes IMG_1318.MOV and saves frames to separate folders:
- heuristic_frames/: Frames where heuristic detected fire/smoke colors
- yolo_detected_frames/: Frames where YOLO confirmed actual hazards
"""
import sys
import os
import cv2
import numpy as np
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from embereye.core.vision_detector import VisionDetector
from embereye.core.detection_queue import get_detection_queue, FrameMetadata
from embereye.core.detection_worker import get_detection_worker, stop_detection_worker

class VideoTestProcessor:
    def __init__(self, video_path, output_base='test_output'):
        self.video_path = video_path
        self.output_base = Path(output_base)
        
        # Create output directories
        self.heuristic_dir = self.output_base / 'heuristic_frames'
        self.yolo_dir = self.output_base / 'yolo_detected_frames'
        self.heuristic_dir.mkdir(parents=True, exist_ok=True)
        self.yolo_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize detection components
        print("[INIT] Initializing VisionDetector (heuristic only)...")
        self.vision_detector = VisionDetector(yolo_model_path="__no_model__")
        
        print("[INIT] Initializing DetectionQueue and Worker...")
        self.detection_queue = get_detection_queue()
        self.detection_worker = get_detection_worker(self.on_yolo_result)
        
        # Tracking
        self.frame_id = 0
        self.heuristic_count = 0
        self.yolo_count = 0
        self.pending_frames = {}  # frame_id -> frame_data
        
        # Thresholds
        self.heuristic_threshold = 0.20  # Queue for YOLO if >= 0.20
        self.yolo_threshold = 0.50  # Save if YOLO >= 0.50
        
        print(f"[CONFIG] Heuristic threshold: {self.heuristic_threshold}")
        print(f"[CONFIG] YOLO threshold: {self.yolo_threshold}")
        print(f"[CONFIG] Output directory: {self.output_base.absolute()}")
        
    def on_yolo_result(self, result):
        """Callback when YOLO processes a queued frame"""
        try:
            if not result:
                return
            
            # Extract from DetectionResult dataclass
            frame_id_str = result.frame_id  # e.g., "video_test-00123"
            status = result.status
            confidence = result.confidence
            detections = result.detections
            primary_class = result.primary_class
            
            # Extract numeric frame_id from string
            try:
                frame_id_num = int(frame_id_str.split('-')[-1])
            except:
                frame_id_num = -1
            
            print(f"[YOLO_RESULT] Frame {frame_id_str}: status={status}, conf={confidence:.3f}, class={primary_class}, detections={len(detections)}")
            
            # Retrieve the frame from pending (needed for saving)
            frame_found = frame_id_num in self.pending_frames
            
            if not frame_found:
                print(f"[DEBUG] Frame {frame_id_num} not found in pending_frames. Available: {list(self.pending_frames.keys())[:5]}")
                # IMPORTANT: Still save this frame even without the original
                # This helps us see what YOLO is detecting
            
            frame_data = None
            if frame_found:
                frame_data = self.pending_frames[frame_id_num]
                frame = frame_data['frame']
                heuristic_score = frame_data['heuristic_score']
            else:
                # Frame not in pending - might be cleaned up, but still log the detection
                heuristic_score = -1
                frame = None
            
            # Save ANY detection YOLO makes (regardless of threshold) for debugging
            # This shows us what model is actually detecting
            if len(detections) > 0 or confidence > 0:
                if frame is None:
                    print(f"[YOLO_DEBUG] Frame unavailable but YOLO detected: {primary_class} ({confidence:.3f})")
                else:
                    # Draw YOLO detections on frame
                    annotated_frame = frame.copy()
                    for det in detections:
                        bbox = det.get('bbox', [])
                        cls = det.get('class', '')
                        conf = det.get('confidence', 0.0)
                        
                        if len(bbox) == 4:
                            x1, y1, x2, y2 = map(int, bbox)
                            # Draw bounding box
                            color = (0, 0, 255) if status == 'CONFIRMED' else (0, 165, 255)
                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                            # Draw label
                            label = f"{cls} {conf:.2f}"
                            cv2.putText(annotated_frame, label, (x1, y1-10), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    
                    # Add info overlay
                    heur_text = f"{heuristic_score:.3f}" if heuristic_score >= 0 else "N/A"
                    info_text = f"YOLO: {status} ({confidence:.3f}) | Heuristic: {heur_text}"
                    cv2.putText(annotated_frame, info_text, (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # Check threshold
                    if confidence >= self.yolo_threshold:
                        # High confidence - save to detected folder
                        output_path = self.yolo_dir / f"frame_{frame_id_num:05d}_yolo_{confidence:.3f}_{primary_class}.jpg"
                        cv2.imwrite(str(output_path), annotated_frame)
                        self.yolo_count += 1
                        print(f"[YOLO_SAVE] Saved to detected: {output_path.name}")
                    else:
                        # Low confidence - save to debug folder
                        debug_dir = self.output_base / 'yolo_low_confidence'
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        output_path = debug_dir / f"frame_{frame_id_num:05d}_{status}_{confidence:.3f}_{primary_class}.jpg"
                        cv2.imwrite(str(output_path), annotated_frame)
                        print(f"[YOLO_DEBUG] Saved to low_confidence: {output_path.name}")
            
            # Clean up pending frame
            if frame_id_num in self.pending_frames:
                del self.pending_frames[frame_id_num]
        except Exception as e:
            print(f"[ERROR] YOLO result handler: {e}")
    
    def process_video(self):
        """Process video file frame by frame"""
        print(f"\n[VIDEO] Opening: {self.video_path}")
        cap = cv2.VideoCapture(str(self.video_path))
        
        if not cap.isOpened():
            print(f"[ERROR] Could not open video: {self.video_path}")
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"[VIDEO] FPS: {fps}, Total frames: {total_frames}")
        
        print("\n[PROCESSING] Starting frame-by-frame analysis...\n")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Run heuristic detection
            heuristic_score = self.vision_detector.heuristic_fire_smoke(frame)
            
            progress = (self.frame_id / total_frames * 100) if total_frames > 0 else 0
            print(f"[FRAME {self.frame_id:05d}] Heuristic: {heuristic_score:.3f} ({progress:.1f}%)")
            
            # Save if heuristic detected something
            if heuristic_score >= self.heuristic_threshold:
                # Save to heuristic folder
                annotated_frame = frame.copy()
                info_text = f"Heuristic: {heuristic_score:.3f}"
                cv2.putText(annotated_frame, info_text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 165, 0), 2)
                
                output_path = self.heuristic_dir / f"frame_{self.frame_id:05d}_heur_{heuristic_score:.3f}.jpg"
                cv2.imwrite(str(output_path), annotated_frame)
                self.heuristic_count += 1
                print(f"  -> Heuristic DETECTED, saved to: {output_path.name}")
                
                # Queue for YOLO processing
                frame_id = f"video_test-{self.frame_id:05d}"
                metadata = FrameMetadata(
                    frame_id=frame_id,
                    stream_id='video_test',
                    heuristic_score=heuristic_score,
                    frame_data=frame.copy(),
                    timestamp_ms=time.time() * 1000
                )
                
                # Store frame for later retrieval
                self.pending_frames[self.frame_id] = {
                    'frame': frame.copy(),
                    'heuristic_score': heuristic_score
                }
                
                # Add to queue
                self.detection_queue.add_frame(metadata)
                print(f"  -> Queued for YOLO validation")
            
            self.frame_id += 1
            
            # Process every 10th frame for speed (optional)
            # Comment out these lines to process all frames
            # if self.frame_id % 10 != 0:
            #     continue
        
        cap.release()
        
        # Wait for YOLO processing to complete
        print("\n[WAIT] Waiting for YOLO processing to complete...")
        time.sleep(5)  # Give worker time to process queue
        
        # Print summary
        print("\n" + "="*60)
        print("PROCESSING COMPLETE")
        print("="*60)
        print(f"Total frames processed: {self.frame_id}")
        print(f"Heuristic detections: {self.heuristic_count} (saved to {self.heuristic_dir})")
        print(f"YOLO confirmations: {self.yolo_count} (saved to {self.yolo_dir})")
        print(f"\nHeuristic false positive rate: {(self.heuristic_count - self.yolo_count) / max(1, self.heuristic_count) * 100:.1f}%")
        print("="*60)
        
    def cleanup(self):
        """Stop detection worker"""
        print("\n[CLEANUP] Stopping detection worker...")
        stop_detection_worker()


if __name__ == "__main__":
    video_path = "simulators/rtsp/data/IMG_1318.MOV"
    
    if not os.path.exists(video_path):
        print(f"ERROR: Video file not found: {video_path}")
        sys.exit(1)
    
    print("="*60)
    print("HYBRID DETECTION TEST - Video Analysis")
    print("="*60)
    
    processor = VideoTestProcessor(video_path)
    
    try:
        processor.process_video()
    finally:
        processor.cleanup()
    
    print("\nTest complete! Check output folders:")
    print(f"  - Heuristic detections: {processor.heuristic_dir}")
    print(f"  - YOLO confirmations: {processor.yolo_dir}")
