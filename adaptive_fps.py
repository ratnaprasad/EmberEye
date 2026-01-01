"""
Adaptive Frame Rate Controller

Monitors detection queue depth and dynamically adjusts camera FPS
to prevent overload while maximizing throughput.
"""

import time
import logging
import os
import sys
from threading import Lock
from typing import Dict

# Determine log file path - handle both normal Python and PyInstaller frozen apps
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    app_dir = os.path.dirname(sys.executable)
else:
    # Running as normal Python script
    app_dir = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(app_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

# Setup logger (file only, no console)
logging.basicConfig(
    filename=os.path.join(log_dir, 'adaptive_fps.log'),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class AdaptiveFPSController:
    """Controls frame capture rate based on processing backlog.
    
    Strategy:
    - Monitor queue depth (pending detections)
    - Reduce FPS when queue > high_watermark
    - Increase FPS when queue < low_watermark
    - Exponential backoff to prevent oscillation
    """
    
    def __init__(self, 
                 base_fps: int = 25,
                 min_fps: int = 5,
                 max_fps: int = 30,
                 high_watermark: int = 8,
                 low_watermark: int = 2,
                 adjustment_interval: float = 2.0):
        """
        Args:
            base_fps: Initial target FPS
            min_fps: Minimum allowed FPS under load
            max_fps: Maximum allowed FPS
            high_watermark: Queue depth triggering FPS reduction
            low_watermark: Queue depth allowing FPS increase
            adjustment_interval: Seconds between adjustments
        """
        self.base_fps = base_fps
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark
        self.adjustment_interval = adjustment_interval
        
        self._lock = Lock()
        self._current_fps: Dict[str, int] = {}  # stream_id -> fps
        self._last_adjustment: Dict[str, float] = {}  # stream_id -> timestamp
        self._adjustment_cooldown = 1.0  # minimum seconds between adjustments
        
    def get_fps(self, stream_id: str) -> int:
        """Get current FPS for stream."""
        with self._lock:
            return self._current_fps.get(stream_id, self.base_fps)
    
    def get_interval_ms(self, stream_id: str) -> int:
        """Get timer interval in milliseconds for stream."""
        fps = self.get_fps(stream_id)
        return int(1000 / fps)
    
    def update(self, stream_id: str, queue_depth: int) -> int:
        """Update FPS based on queue depth.
        
        Args:
            stream_id: Unique identifier for video stream
            queue_depth: Current number of pending detections
            
        Returns:
            New FPS value (may be unchanged)
        """
        with self._lock:
            current_fps = self._current_fps.get(stream_id, self.base_fps)
            last_adj = self._last_adjustment.get(stream_id, 0)
            now = time.time()
            
            # Check cooldown
            if now - last_adj < self._adjustment_cooldown:
                return current_fps
            
            new_fps = current_fps
            
            # Reduce FPS if queue is backing up
            if queue_depth >= self.high_watermark:
                # Aggressive reduction (25% drop)
                new_fps = max(self.min_fps, int(current_fps * 0.75))
                if new_fps != current_fps:
                    logger.debug(f"[AdaptiveFPS] {stream_id}: Reducing FPS {current_fps} -> {new_fps} (queue={queue_depth})")
                    
            # Gradually increase FPS if queue is healthy
            elif queue_depth <= self.low_watermark and current_fps < self.base_fps:
                # Conservative increase (1 FPS at a time)
                new_fps = min(self.base_fps, current_fps + 1)
                if new_fps != current_fps:
                    logger.debug(f"[AdaptiveFPS] {stream_id}: Increasing FPS {current_fps} -> {new_fps} (queue={queue_depth})")
            
            if new_fps != current_fps:
                self._current_fps[stream_id] = new_fps
                self._last_adjustment[stream_id] = now
                
            return new_fps
    
    def reset(self, stream_id: str):
        """Reset stream to base FPS."""
        with self._lock:
            self._current_fps[stream_id] = self.base_fps
            self._last_adjustment.pop(stream_id, None)
            
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get statistics for all streams."""
        with self._lock:
            return {
                sid: {
                    'current_fps': fps,
                    'base_fps': self.base_fps,
                    'utilization': fps / self.base_fps
                }
                for sid, fps in self._current_fps.items()
            }


# Global instance for shared use
_global_controller = AdaptiveFPSController()


def get_controller() -> AdaptiveFPSController:
    """Get global adaptive FPS controller instance."""
    return _global_controller
