"""
Async Detection Queue System
Manages frame queuing and YOLO processing for multiple streams
"""
import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, List
from pathlib import Path


@dataclass
class DetectionResult:
    """Result from YOLO inference"""
    frame_id: str  # "stream_id-frame_number"
    stream_id: str
    status: str  # "CONFIRMED" | "POSSIBLE" | "LOW"
    confidence: float  # 0.0-1.0 (highest detection confidence)
    detections: List[Dict] = field(default_factory=list)  # [{'class': 'FIRE', 'conf': 0.78}, ...]
    primary_class: str = ""  # e.g., 'SMOKE_WITH_FIRE'
    yolo_latency_ms: float = 0.0
    timestamp_ms: float = 0.0
    
    def __repr__(self):
        return f"[{self.status}] {self.primary_class} ({self.confidence:.2f}) - {self.stream_id}"


@dataclass
class FrameMetadata:
    """Frame queued for YOLO processing"""
    frame_id: str  # "stream_id-frame_number"
    stream_id: str
    heuristic_score: float
    frame_data: Optional[object] = None  # numpy array or reference
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000)
    
    def age_ms(self) -> float:
        return time.time() * 1000 - self.timestamp_ms


class DetectionQueue:
    """
    Thread-safe queue for managing frames pending YOLO detection.
    
    Features:
    - Async processing (frames added without waiting)
    - Per-stream tracking
    - Result caching
    - Backpressure handling (drop old frames if queue full)
    """
    
    def __init__(self, max_queue_size: int = 100, result_cache_size: int = 500):
        self.max_queue_size = max_queue_size
        self.queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        
        # Result cache: {frame_id: DetectionResult}
        self.result_cache: Dict[str, DetectionResult] = {}
        self.result_cache_size = result_cache_size
        self.result_cache_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'total_queued': 0,
            'total_processed': 0,
            'total_dropped': 0,
            'queue_overflow': 0,
            'avg_queue_wait_ms': 0.0,
        }
        self.stats_lock = threading.Lock()
    
    def add_frame(self, frame_metadata: FrameMetadata) -> bool:
        """
        Add frame to detection queue.
        
        Returns:
            True if frame added successfully
            False if queue full (frame dropped due to backpressure)
        """
        try:
            # Try to add without blocking
            self.queue.put_nowait(frame_metadata)
            with self.stats_lock:
                self.stats['total_queued'] += 1
            return True
        except queue.Full:
            # Queue overflow - drop oldest frames and retry
            with self.stats_lock:
                self.stats['queue_overflow'] += 1
                self.stats['total_dropped'] += 1
            
            # Try to make space by removing oldest
            try:
                self.queue.get_nowait()
                # Retry adding
                self.queue.put_nowait(frame_metadata)
                with self.stats_lock:
                    self.stats['total_queued'] += 1
                return True
            except queue.Empty:
                return False
    
    def get_frame(self, timeout_s: float = 0.1) -> Optional[FrameMetadata]:
        """
        Get next frame from queue.
        
        Args:
            timeout_s: How long to wait if queue is empty
        
        Returns:
            FrameMetadata or None if queue empty
        """
        try:
            frame = self.queue.get(timeout=timeout_s)
            return frame
        except queue.Empty:
            return None
    
    def cache_result(self, result: DetectionResult) -> None:
        """Cache YOLO detection result"""
        with self.result_cache_lock:
            self.result_cache[result.frame_id] = result
            
            # Keep cache bounded
            if len(self.result_cache) > self.result_cache_size:
                # Remove oldest entry
                oldest_key = min(
                    self.result_cache.keys(),
                    key=lambda k: self.result_cache[k].timestamp_ms
                )
                del self.result_cache[oldest_key]
            
            with self.stats_lock:
                self.stats['total_processed'] += 1
    
    def get_result(self, frame_id: str) -> Optional[DetectionResult]:
        """Retrieve cached detection result"""
        with self.result_cache_lock:
            return self.result_cache.get(frame_id)
    
    def clear_result(self, frame_id: str) -> None:
        """Remove result from cache"""
        with self.result_cache_lock:
            self.result_cache.pop(frame_id, None)
    
    def get_queue_size(self) -> int:
        """Current queue depth"""
        return self.queue.qsize()
    
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        with self.stats_lock:
            return {
                'queue_size': self.get_queue_size(),
                **self.stats
            }
    
    def reset_stats(self) -> None:
        """Reset statistics counters"""
        with self.stats_lock:
            for key in self.stats:
                if isinstance(self.stats[key], (int, float)):
                    self.stats[key] = 0


# Global detection queue instance (shared across all streams)
_global_detection_queue: Optional[DetectionQueue] = None
_queue_lock = threading.Lock()


def get_detection_queue() -> DetectionQueue:
    """Get or create global detection queue"""
    global _global_detection_queue
    if _global_detection_queue is None:
        with _queue_lock:
            if _global_detection_queue is None:
                _global_detection_queue = DetectionQueue()
    return _global_detection_queue
