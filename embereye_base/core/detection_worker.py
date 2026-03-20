"""
Detection Worker Thread
Processes frames from detection queue with YOLO model in background thread
"""
import threading
import time
import os
import filecmp
from pathlib import Path
from typing import Callable, Optional, Dict
from .detection_queue import get_detection_queue, DetectionResult
from .hybrid_detector import HybridDetector


class DetectionWorker(threading.Thread):
    """
    Background worker thread that:
    1. Polls detection queue for frames
    2. Runs YOLO inference on each frame
    3. Caches results
    4. Calls result callbacks
    """
    
    def __init__(self, 
                 model_path: Optional[str] = None,
                 result_callback: Optional[Callable[[DetectionResult], None]] = None,
                 max_latency_ms: float = 1500.0,
                 daemon: bool = True):
        """
        Args:
            model_path: Path to YOLO model (auto-detected if None)
            result_callback: Function to call when result is ready
            max_latency_ms: Max time to wait before dropping old frames
            daemon: If True, worker exits when main thread exits
        """
        super().__init__(daemon=daemon)
        self.name = "DetectionWorker"
        
        self.detection_queue = get_detection_queue()
        self.detector = HybridDetector(model_path=model_path, stream_id="worker")
        
        self.result_callbacks = []
        if result_callback:
            self.result_callbacks.append(result_callback)
        self.max_latency_ms = max_latency_ms
        
        self._stop_event = threading.Event()
        self._paused_event = threading.Event()
        
        self.stats = {
            'frames_processed': 0,
            'frames_dropped': 0,
            'avg_inference_ms': 0.0,
            'total_inference_ms': 0.0,
            'detections_confirmed': 0,
        }
    
    def run(self) -> None:
        """Main worker loop"""
        print("[DetectionWorker] Started")
        
        while not self._stop_event.is_set():
            # Handle pause
            if self._paused_event.is_set():
                time.sleep(0.1)
                continue
            
            # Get next frame from queue
            metadata = self.detection_queue.get_frame(timeout_s=0.5)
            
            if metadata is None:
                # Queue empty, brief sleep
                time.sleep(0.01)
                continue
            
            # Check if frame is too old
            age_ms = metadata.age_ms()
            if age_ms > self.max_latency_ms:
                # Drop old frame
                with self.detection_queue.stats_lock:
                    self.detection_queue.stats['total_dropped'] += 1
                self.stats['frames_dropped'] += 1
                continue
            
            # Process frame with YOLO
            try:
                result = self.detector.process_queued_frame(metadata)
                
                # Cache result
                self.detection_queue.cache_result(result)
                
                # Call all registered callbacks
                for callback in list(self.result_callbacks):
                    try:
                        callback(result)
                    except Exception as e:
                        print(f"[DetectionWorker] Callback error: {e}")
                
                # Update stats
                self.stats['frames_processed'] += 1
                if result.status in ("CONFIRMED", "POSSIBLE") and result.detections:
                    self.stats['detections_confirmed'] += 1
                self.stats['total_inference_ms'] += result.yolo_latency_ms
                if self.stats['frames_processed'] > 0:
                    self.stats['avg_inference_ms'] = (
                        self.stats['total_inference_ms'] / self.stats['frames_processed']
                    )
                
                # Log occasionally
                if self.stats['frames_processed'] % 50 == 0:
                    print(f"[DetectionWorker] Processed {self.stats['frames_processed']} frames, "
                          f"Avg latency: {self.stats['avg_inference_ms']:.0f}ms")
            
            except Exception as e:
                print(f"[DetectionWorker] Processing error: {e}")
                self.stats['frames_dropped'] += 1
    
    def stop(self) -> None:
        """Signal worker to stop"""
        self._stop_event.set()
        print("[DetectionWorker] Stopping...")
    
    def pause(self) -> None:
        """Pause processing"""
        self._paused_event.set()
        print("[DetectionWorker] Paused")
    
    def resume(self) -> None:
        """Resume processing"""
        self._paused_event.clear()
        print("[DetectionWorker] Resumed")
    
    def is_running(self) -> bool:
        """Check if worker is running"""
        return self.is_alive() and not self._stop_event.is_set()

    def _resolve_model_version(self, model_path: Optional[str]) -> Optional[str]:
        """Best-effort resolve of active model version for UI display."""
        if not model_path:
            return None

        path_obj = Path(model_path)
        parts = path_obj.parts

        # Fast path when the file is already under models/<version>/weights/*
        if 'models' in parts:
            try:
                idx = parts.index('models')
                if idx + 1 < len(parts):
                    candidate = parts[idx + 1]
                    if candidate and candidate != 'yolo_versions':
                        return candidate
            except Exception:
                pass

        # Alias path path: models/yolo_versions/current_best.pt
        if path_obj.name.lower() == 'current_best.pt':
            try:
                from embereye_base.core.model_versioning import ModelVersionManager

                manager = ModelVersionManager()
                # Support both classic vN folders and deployment_* import folders.
                version_dirs = [
                    p for p in manager.models_dir.iterdir()
                    if p.is_dir() and (p / "weights" / "EmberEye.pt").exists()
                ]
                for version_dir in version_dirs:
                    version = version_dir.name
                    version_file = version_dir / "weights" / "EmberEye.pt"
                    if not version_file.exists():
                        continue

                    # Symlink-friendly fast check.
                    try:
                        if os.path.samefile(str(path_obj), str(version_file)):
                            return version
                    except Exception:
                        pass

                    # Windows fallback when current_best.pt is copied (not symlinked).
                    try:
                        if filecmp.cmp(str(path_obj), str(version_file), shallow=False):
                            return version
                    except Exception:
                        continue
            except Exception:
                return None

        return None
    
    def get_stats(self) -> Dict:
        """Get worker statistics"""
        model_path = getattr(self.detector, 'yolo_model_path', None)
        model_name = Path(model_path).name if model_path else None
        model_version = self._resolve_model_version(model_path)
        return {
            **self.stats,
            'queue_size': self.detection_queue.get_queue_size(),
            'queue_stats': self.detection_queue.get_stats(),
            'model_loaded': self.detector.model_loaded,
            'model_error': self.detector.last_load_error,
            'inference_device': getattr(self.detector, 'inference_device', 'cpu'),
            'model_path': model_path,
            'model_name': model_name,
            'model_version': model_version,
        }

    def add_result_callback(self, callback: Optional[Callable[[DetectionResult], None]]) -> None:
        """Register an additional callback for detection results."""
        if not callback:
            return
        if callback not in self.result_callbacks:
            self.result_callbacks.append(callback)
    
    def reset_stats(self) -> None:
        """Reset statistics"""
        for key in self.stats:
            if isinstance(self.stats[key], (int, float)):
                self.stats[key] = 0


# Global worker instance
_global_worker: Optional[DetectionWorker] = None
_worker_lock = threading.Lock()


def get_detection_worker(result_callback: Optional[Callable] = None) -> DetectionWorker:
    """Get or create global detection worker"""
    global _global_worker
    if _global_worker is None or not _global_worker.is_running():
        with _worker_lock:
            if _global_worker is None or not _global_worker.is_running():
                _global_worker = DetectionWorker(result_callback=result_callback)
                _global_worker.start()
    elif result_callback is not None:
        _global_worker.add_result_callback(result_callback)
    return _global_worker


def stop_detection_worker() -> None:
    """Stop global detection worker"""
    global _global_worker
    if _global_worker and _global_worker.is_running():
        _global_worker.stop()
        _global_worker.join(timeout=5.0)
        print("[DetectionWorker] Stopped")
