"""
Prometheus Metrics Exporter for EmberEye

Exposes system metrics via HTTP endpoint for Prometheus scraping.
"""

import time
from threading import Lock, Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any


class MetricsCollector:
    """Thread-safe metrics collection."""
    
    def __init__(self):
        self._lock = Lock()
        
        # Camera metrics
        self.frames_processed_total: Dict[str, int] = {}
        self.frames_dropped_total: Dict[str, int] = {}
        self.vision_detection_latency_sum: Dict[str, float] = {}
        self.vision_detection_count: Dict[str, int] = {}
        self.current_fps: Dict[str, float] = {}
        self.detection_queue_depth: Dict[str, int] = {}
        
        # TCP sensor metrics
        self.tcp_packets_received_total: Dict[str, int] = {}
        self.tcp_packets_error_total: Dict[str, int] = {}
        self.tcp_packet_latency_sum: Dict[str, float] = {}
        self.tcp_packet_count: Dict[str, int] = {}
        self.tcp_queue_depth = 0
        self.tcp_connections_active = 0
        
        # Sensor fusion metrics
        self.fusion_invocations_total = 0
        self.fusion_alarms_total = 0
        self.fusion_latency_sum = 0.0
        self.fusion_count = 0
        
        # System metrics
        self.start_time = time.time()
        
    def record_frame_processed(self, stream_id: str):
        with self._lock:
            self.frames_processed_total[stream_id] = self.frames_processed_total.get(stream_id, 0) + 1
    
    def record_frame_dropped(self, stream_id: str):
        with self._lock:
            self.frames_dropped_total[stream_id] = self.frames_dropped_total.get(stream_id, 0) + 1
    
    def record_vision_latency(self, stream_id: str, latency_ms: float):
        with self._lock:
            self.vision_detection_latency_sum[stream_id] = self.vision_detection_latency_sum.get(stream_id, 0) + latency_ms
            self.vision_detection_count[stream_id] = self.vision_detection_count.get(stream_id, 0) + 1
    
    def update_fps(self, stream_id: str, fps: float):
        with self._lock:
            self.current_fps[stream_id] = fps
    
    def update_detection_queue_depth(self, stream_id: str, depth: int):
        with self._lock:
            self.detection_queue_depth[stream_id] = depth
    
    def record_tcp_packet(self, loc_id: str, latency_ms: float = 0):
        with self._lock:
            self.tcp_packets_received_total[loc_id] = self.tcp_packets_received_total.get(loc_id, 0) + 1
            if latency_ms > 0:
                self.tcp_packet_latency_sum[loc_id] = self.tcp_packet_latency_sum.get(loc_id, 0) + latency_ms
                self.tcp_packet_count[loc_id] = self.tcp_packet_count.get(loc_id, 0) + 1
    
    def record_tcp_error(self, loc_id: str):
        with self._lock:
            self.tcp_packets_error_total[loc_id] = self.tcp_packets_error_total.get(loc_id, 0) + 1
    
    def update_tcp_queue_depth(self, depth: int):
        with self._lock:
            self.tcp_queue_depth = depth
    
    def update_tcp_connections(self, count: int):
        with self._lock:
            self.tcp_connections_active = count
    
    def record_fusion(self, alarm: bool, latency_ms: float = 0):
        with self._lock:
            self.fusion_invocations_total += 1
            if alarm:
                self.fusion_alarms_total += 1
            if latency_ms > 0:
                self.fusion_latency_sum += latency_ms
                self.fusion_count += 1
    
    def export_prometheus(self) -> str:
        """Generate Prometheus-format metrics text."""
        with self._lock:
            lines = [
                "# HELP emberye_uptime_seconds Time since application start",
                "# TYPE emberye_uptime_seconds gauge",
                f"emberye_uptime_seconds {time.time() - self.start_time:.2f}",
                "",
                "# HELP emberye_frames_processed_total Total frames processed by camera stream",
                "# TYPE emberye_frames_processed_total counter"
            ]
            
            for sid, count in self.frames_processed_total.items():
                lines.append(f'emberye_frames_processed_total{{stream_id="{sid}"}} {count}')
            
            lines.extend([
                "",
                "# HELP emberye_frames_dropped_total Total frames dropped due to backpressure",
                "# TYPE emberye_frames_dropped_total counter"
            ])
            
            for sid, count in self.frames_dropped_total.items():
                lines.append(f'emberye_frames_dropped_total{{stream_id="{sid}"}} {count}')
            
            lines.extend([
                "",
                "# HELP emberye_vision_detection_latency_avg_ms Average vision detection latency",
                "# TYPE emberye_vision_detection_latency_avg_ms gauge"
            ])
            
            for sid in self.vision_detection_count:
                count = self.vision_detection_count[sid]
                if count > 0:
                    avg = self.vision_detection_latency_sum[sid] / count
                    lines.append(f'emberye_vision_detection_latency_avg_ms{{stream_id="{sid}"}} {avg:.2f}')
            
            lines.extend([
                "",
                "# HELP emberye_current_fps Current frames per second by stream",
                "# TYPE emberye_current_fps gauge"
            ])
            
            for sid, fps in self.current_fps.items():
                lines.append(f'emberye_current_fps{{stream_id="{sid}"}} {fps:.2f}')
            
            lines.extend([
                "",
                "# HELP emberye_detection_queue_depth Current detection queue depth",
                "# TYPE emberye_detection_queue_depth gauge"
            ])
            
            for sid, depth in self.detection_queue_depth.items():
                lines.append(f'emberye_detection_queue_depth{{stream_id="{sid}"}} {depth}')
            
            lines.extend([
                "",
                "# HELP emberye_tcp_packets_received_total Total TCP packets received",
                "# TYPE emberye_tcp_packets_received_total counter"
            ])
            
            for loc, count in self.tcp_packets_received_total.items():
                lines.append(f'emberye_tcp_packets_received_total{{location_id="{loc}"}} {count}')
            
            lines.extend([
                "",
                "# HELP emberye_tcp_packets_error_total Total TCP packet errors",
                "# TYPE emberye_tcp_packets_error_total counter"
            ])
            
            for loc, count in self.tcp_packets_error_total.items():
                lines.append(f'emberye_tcp_packets_error_total{{location_id="{loc}"}} {count}')
            
            lines.extend([
                "",
                "# HELP emberye_tcp_packet_latency_avg_ms Average TCP packet processing latency",
                "# TYPE emberye_tcp_packet_latency_avg_ms gauge"
            ])
            
            for loc in self.tcp_packet_count:
                count = self.tcp_packet_count[loc]
                if count > 0:
                    avg = self.tcp_packet_latency_sum[loc] / count
                    lines.append(f'emberye_tcp_packet_latency_avg_ms{{location_id="{loc}"}} {avg:.2f}')
            
            lines.extend([
                "",
                "# HELP emberye_tcp_queue_depth Current TCP packet queue depth",
                "# TYPE emberye_tcp_queue_depth gauge",
                f"emberye_tcp_queue_depth {self.tcp_queue_depth}",
                "",
                "# HELP emberye_tcp_connections_active Active TCP connections",
                "# TYPE emberye_tcp_connections_active gauge",
                f"emberye_tcp_connections_active {self.tcp_connections_active}",
                "",
                "# HELP emberye_fusion_invocations_total Total sensor fusion invocations",
                "# TYPE emberye_fusion_invocations_total counter",
                f"emberye_fusion_invocations_total {self.fusion_invocations_total}",
                "",
                "# HELP emberye_fusion_alarms_total Total fusion alarms triggered",
                "# TYPE emberye_fusion_alarms_total counter",
                f"emberye_fusion_alarms_total {self.fusion_alarms_total}",
                "",
                "# HELP emberye_fusion_latency_avg_ms Average fusion processing latency",
                "# TYPE emberye_fusion_latency_avg_ms gauge"
            ])
            
            if self.fusion_count > 0:
                avg = self.fusion_latency_sum / self.fusion_count
                lines.append(f"emberye_fusion_latency_avg_ms {avg:.2f}")
            else:
                lines.append("emberye_fusion_latency_avg_ms 0")
            
            return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus scrape endpoint."""
    
    collector: MetricsCollector = None  # Set by MetricsServer
    
    def do_GET(self):
        if self.path == '/metrics':
            try:
                metrics = self.collector.export_prometheus()
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; version=0.0.4')
                self.end_headers()
                self.wfile.write(metrics.encode('utf-8'))
            except Exception as e:
                self.send_error(500, f"Metrics export error: {e}")
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK\n")
        else:
            self.send_error(404, "Not Found")
    
    def log_message(self, format, *args):
        """Suppress default logging to avoid console spam."""
        pass


class MetricsServer:
    """HTTP server exposing Prometheus metrics."""
    
    def __init__(self, collector: MetricsCollector, port: int = 9090, host: str = '0.0.0.0'):
        self.collector = collector
        self.port = port
        self.host = host
        self.server: HTTPServer | None = None
        self.thread: Thread | None = None
        
    def start(self):
        """Start metrics HTTP server in background thread."""
        if self.server:
            return
        
        MetricsHandler.collector = self.collector
        self.server = HTTPServer((self.host, self.port), MetricsHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"Metrics server started on http://{self.host}:{self.port}/metrics")
    
    def stop(self):
        """Stop metrics server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None


# Global metrics collector instance
_global_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get global metrics collector instance."""
    return _global_metrics
