"""
Async Detection Queue System
Manages frame queuing and YOLO processing for multiple streams
"""
import threading
import queue
import time
import os
from collections import defaultdict, deque
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
    
    def __init__(self, max_queue_size: int = 100, result_cache_size: int = 500, per_stream_max: int = 4):
        self.max_queue_size = max_queue_size
        self.per_stream_max = max(1, per_stream_max)

        # Per-stream bounded buffers + fair scheduler state
        self.stream_queues: Dict[str, deque] = {}
        self.active_streams: List[str] = []
        self._next_stream_idx = 0
        self._total_queued_items = 0
        self._total_dequeued_items = 0
        self._queue_lock = threading.Lock()
        self._not_empty = threading.Condition(self._queue_lock)
        
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
            'per_stream_dropped': {},
            'avg_queue_wait_ms': 0.0,
        }
        self.stats_lock = threading.Lock()

    def _drop_oldest_from_stream_unlocked(self, stream_id: str) -> bool:
        """Drop oldest frame from a specific stream. Caller must hold _queue_lock."""
        stream_queue = self.stream_queues.get(stream_id)
        if not stream_queue:
            return False
        stream_queue.popleft()
        self._total_queued_items = max(0, self._total_queued_items - 1)

        if len(stream_queue) == 0:
            self.stream_queues.pop(stream_id, None)
            if stream_id in self.active_streams:
                idx = self.active_streams.index(stream_id)
                self.active_streams.pop(idx)
                if self.active_streams:
                    self._next_stream_idx %= len(self.active_streams)
                else:
                    self._next_stream_idx = 0

        with self.stats_lock:
            self.stats['total_dropped'] += 1
            self.stats['queue_overflow'] += 1
            dropped_map = self.stats['per_stream_dropped']
            dropped_map[stream_id] = dropped_map.get(stream_id, 0) + 1
        return True

    def _drop_oldest_global_unlocked(self) -> bool:
        """Drop globally oldest frame across stream heads. Caller must hold _queue_lock."""
        if not self.stream_queues:
            return False
        oldest_stream = None
        oldest_ts = None
        for stream_id, stream_queue in self.stream_queues.items():
            if not stream_queue:
                continue
            head_ts = stream_queue[0].timestamp_ms
            if oldest_ts is None or head_ts < oldest_ts:
                oldest_ts = head_ts
                oldest_stream = stream_id
        if oldest_stream is None:
            return False
        return self._drop_oldest_from_stream_unlocked(oldest_stream)
    
    def add_frame(self, frame_metadata: FrameMetadata) -> bool:
        """
        Add frame to detection queue.
        
        Returns:
            True if frame added successfully
            False if queue full (frame dropped due to backpressure)
        """
        stream_id = str(frame_metadata.stream_id)
        with self._queue_lock:
            stream_queue = self.stream_queues.get(stream_id)
            if stream_queue is None:
                stream_queue = deque()
                self.stream_queues[stream_id] = stream_queue

            # Per-stream backpressure: keep only freshest N per stream
            if len(stream_queue) >= self.per_stream_max:
                self._drop_oldest_from_stream_unlocked(stream_id)
                stream_queue = self.stream_queues.get(stream_id)
                if stream_queue is None:
                    stream_queue = deque()
                    self.stream_queues[stream_id] = stream_queue

            # Global backpressure: bound total memory/latency
            while self._total_queued_items >= self.max_queue_size:
                if not self._drop_oldest_global_unlocked():
                    break

            stream_queue.append(frame_metadata)
            self._total_queued_items += 1
            if stream_id not in self.active_streams:
                self.active_streams.append(stream_id)

            with self.stats_lock:
                self.stats['total_queued'] += 1

            self._not_empty.notify()
            return True
    
    def get_frame(self, timeout_s: float = 0.1) -> Optional[FrameMetadata]:
        """
        Get next frame from queue.
        
        Args:
            timeout_s: How long to wait if queue is empty
        
        Returns:
            FrameMetadata or None if queue empty
        """
        deadline = time.time() + timeout_s
        with self._not_empty:
            while self._total_queued_items == 0:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._not_empty.wait(timeout=remaining)

            if not self.active_streams:
                return None

            self._next_stream_idx %= len(self.active_streams)
            stream_id = self.active_streams[self._next_stream_idx]
            stream_queue = self.stream_queues.get(stream_id)
            if not stream_queue:
                self.active_streams.pop(self._next_stream_idx)
                if not self.active_streams:
                    self._next_stream_idx = 0
                    return None
                self._next_stream_idx %= len(self.active_streams)
                stream_id = self.active_streams[self._next_stream_idx]
                stream_queue = self.stream_queues.get(stream_id)
                if not stream_queue:
                    return None

            frame = stream_queue.popleft()
            self._total_queued_items = max(0, self._total_queued_items - 1)
            self._total_dequeued_items += 1

            if len(stream_queue) == 0:
                self.stream_queues.pop(stream_id, None)
                self.active_streams.pop(self._next_stream_idx)
                if self.active_streams:
                    self._next_stream_idx %= len(self.active_streams)
                else:
                    self._next_stream_idx = 0
            else:
                self._next_stream_idx = (self._next_stream_idx + 1) % len(self.active_streams)

            wait_ms = frame.age_ms()
            with self.stats_lock:
                processed = max(1, self._total_dequeued_items)
                prev_avg = self.stats['avg_queue_wait_ms']
                self.stats['avg_queue_wait_ms'] = prev_avg + ((wait_ms - prev_avg) / processed)

            return frame
    
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
        with self._queue_lock:
            return self._total_queued_items
    
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        with self._queue_lock:
            queue_size = self._total_queued_items
            active_stream_count = len(self.active_streams)
        with self.stats_lock:
            return {
                'queue_size': queue_size,
                'active_streams': active_stream_count,
                'per_stream_max': self.per_stream_max,
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
                max_queue_size = int(os.environ.get("EMBEREYE_DETECTION_QUEUE_MAX", "1000"))
                per_stream_max = int(os.environ.get("EMBEREYE_DETECTION_QUEUE_PER_STREAM_MAX", "4"))
                result_cache_size = int(os.environ.get("EMBEREYE_DETECTION_RESULT_CACHE_MAX", "1000"))
                _global_detection_queue = DetectionQueue(
                    max_queue_size=max_queue_size,
                    result_cache_size=result_cache_size,
                    per_stream_max=per_stream_max,
                )
    return _global_detection_queue
