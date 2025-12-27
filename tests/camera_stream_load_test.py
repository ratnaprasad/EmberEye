#!/usr/bin/env python3
"""
Camera Stream Load Test Harness for EmberEye

This script can stress-test fire/smoke vision detection and (optionally) the
`VideoWorker` pipeline by simulating multiple concurrent camera streams.

Modes:
  direct      -> Uses VisionDetector directly on synthetic frames (fast, headless)
  monkeypatch -> Monkeypatches cv2.VideoCapture so existing VideoWorker instances
                 believe they are reading from real cameras; exercises signal flow.

Usage Examples:
  python camera_stream_load_test.py --streams 4 --frames 500 --fps 30 --mode direct
  python camera_stream_load_test.py --streams 3 --duration 10 --fps 25 --mode monkeypatch

Parameters (either --frames or --duration is required):
  --streams N      Number of concurrent synthetic camera feeds
  --frames N       Total frames per stream to process (mutually exclusive with --duration)
  --duration SEC   Duration (seconds) to run instead of fixed frame count
  --fps N          Target frames per second per stream (synthetic generation)
  --width W        Frame width (default 640)
  --height H       Frame height (default 480)
  --mode {direct,monkeypatch}
  --report-interval SEC   Interval for periodic progress logging (default 2)
  --stats-file PATH        Optional JSON output with aggregated results
  --seed INT               RNG seed for reproducibility

Outputs:
  Prints per-stream latency stats, aggregate FPS, optional CPU/memory metrics.
  In monkeypatch mode, it also counts frames emitted via VideoWorker.frame_ready.

Notes:
  - psutil metrics are included if psutil is installed; otherwise skipped.
  - Synthetic frames are random uint8 BGR arrays.
  - VisionDetector heuristic is color-based; random frames produce low scores.
  - For realistic distribution, you could replace random with patterned frames.
"""
from __future__ import annotations
import argparse, time, threading, random, json, statistics, sys, os
from typing import List, Dict, Optional
import numpy as np

# Attempt optional psutil
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

from vision_detector import VisionDetector

def parse_args():
    p = argparse.ArgumentParser(description="EmberEye camera stream load tester")
    p.add_argument('--streams', type=int, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--frames', type=int, help='Number of frames per stream')
    g.add_argument('--duration', type=float, help='Duration (seconds) to run')
    p.add_argument('--fps', type=float, default=30.0, help='Target FPS per stream')
    p.add_argument('--width', type=int, default=640)
    p.add_argument('--height', type=int, default=480)
    p.add_argument('--mode', choices=['direct','monkeypatch'], default='direct')
    p.add_argument('--report-interval', type=float, default=2.0)
    p.add_argument('--stats-file', type=str)
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()

class StreamStats:
    def __init__(self):
        self.latencies: List[float] = []
        self.frames_processed = 0
        self.vision_scores: List[float] = []
        self.start_time = time.time()
    def add(self, latency: float, score: float):
        self.latencies.append(latency)
        self.frames_processed += 1
        self.vision_scores.append(score)
    def summary(self) -> Dict[str, float]:
        dur = time.time() - self.start_time
        return {
            'frames': self.frames_processed,
            'duration_sec': dur,
            'fps': self.frames_processed / dur if dur > 0 else 0.0,
            'latency_avg_ms': statistics.mean(self.latencies)*1000 if self.latencies else 0.0,
            'latency_p95_ms': (statistics.quantiles(self.latencies, n=20)[18]*1000) if len(self.latencies) >= 20 else 0.0,
            'latency_max_ms': max(self.latencies)*1000 if self.latencies else 0.0,
            'vision_score_avg': statistics.mean(self.vision_scores) if self.vision_scores else 0.0,
        }

def run_direct(args):
    random.seed(args.seed)
    streams: List[StreamStats] = [StreamStats() for _ in range(args.streams)]
    detector = VisionDetector()
    stop_time = None
    if args.duration:
        stop_time = time.time() + args.duration
    frame_interval = 1.0 / args.fps if args.fps > 0 else 0

    def worker(idx: int):
        stats = streams[idx]
        target_frames = args.frames if args.frames else float('inf')
        next_frame_deadline = time.time()
        while True:
            if stop_time and time.time() >= stop_time:
                break
            if stats.frames_processed >= target_frames:
                break
            # Pace
            now = time.time()
            if frame_interval > 0 and now < next_frame_deadline:
                time.sleep(max(0, next_frame_deadline - now))
            next_frame_deadline = time.time() + frame_interval
            frame = np.random.randint(0, 256, (args.height, args.width, 3), dtype=np.uint8)
            t0 = time.perf_counter()
            score = detector.detect(frame)
            latency = time.perf_counter() - t0
            stats.add(latency, score)
        
    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.streams)]
    for t in threads: t.start()

    last_report = time.time()
    while any(t.is_alive() for t in threads):
        time.sleep(0.25)
        if time.time() - last_report >= args.report_interval:
            last_report = time.time()
            agg_fps = sum(s.frames_processed for s in streams) / max(1e-9, (time.time() - min(s.start_time for s in streams)))
            print(f"[progress] total_frames={sum(s.frames_processed for s in streams)} agg_fps={agg_fps:.1f}")
    for t in threads: t.join()

    return streams

# Monkeypatch mode: override cv2.VideoCapture so VideoWorker thinks streams opened.
class DummyCapture:
    def __init__(self, index_or_url, width, height):
        self.width = width
        self.height = height
        self.opened = True
    def isOpened(self):
        return self.opened
    def read(self):
        frame = np.random.randint(0,256,(self.height,self.width,3),dtype=np.uint8)
        return True, frame
    def release(self):
        self.opened = False

# We only import PyQt5 and VideoWorker if needed.

def run_monkeypatch(args):
    import cv2  # local import to patch
    from PyQt5.QtWidgets import QApplication
    from video_worker import VideoWorker
    from PyQt5.QtCore import QTimer

    orig_VideoCapture = cv2.VideoCapture
    def patched_VideoCapture(arg, backend=None):  # signature flexible
        return DummyCapture(arg, args.width, args.height)
    cv2.VideoCapture = patched_VideoCapture  # type: ignore

    app = QApplication.instance() or QApplication([])

    workers: List[VideoWorker] = []
    stats: List[StreamStats] = [StreamStats() for _ in range(args.streams)]

    def make_worker(i: int):
        # Use synthetic URL label for identification
        url = f"synthetic://stream{i}"  # Will be formatted but still fine
        vw = VideoWorker(url)
        def on_frame(_pixmap, idx=i):
            # We measure latency only for detection already done inside VideoWorker.update_frame
            stats[idx].add(0.0, 0.0)  # latency placeholder (already measured internally? not exposed)
        vw.frame_ready.connect(on_frame)
        vw.start_stream()
        workers.append(vw)

    for i in range(args.streams):
        make_worker(i)

    frame_interval = 1.0 / args.fps if args.fps > 0 else 0
    stop_time = time.time() + (args.duration if args.duration else ((args.frames or 0) / args.fps))

    # Use a QTimer to call update_frame on all workers
    def tick():
        now = time.time()
        if now >= stop_time:
            for w in workers: w.stop_stream()
            app.quit()
            return
        for w in workers:
            w.update_frame()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(int(max(1, frame_interval*1000)))

    last_progress = time.time()
    def progress_timer():
        while True:
            if not any(w.cap and w.cap.isOpened() for w in workers):
                break
            time.sleep(0.5)
            if time.time() - last_progress >= args.report_interval:
                total = sum(s.frames_processed for s in stats)
                duration = time.time() - min(s.start_time for s in stats)
                agg_fps = total / max(1e-9, duration)
                print(f"[progress] total_frames={total} agg_fps={agg_fps:.1f}")
    pt = threading.Thread(target=progress_timer, daemon=True)
    pt.start()

    app.exec_()
    # Restore original capture
    cv2.VideoCapture = orig_VideoCapture
    return stats


def collect_system_metrics():
    if not psutil:
        return {}
    p = psutil.Process(os.getpid())
    with p.oneshot():
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.2),
            'mem_rss_mb': p.memory_info().rss / (1024*1024),
            'mem_percent': p.memory_percent(),
            'threads': p.num_threads()
        }


def main():
    args = parse_args()
    print(f"Starting load test: mode={args.mode} streams={args.streams} fps={args.fps}")
    if args.mode == 'direct':
        stream_stats = run_direct(args)
    else:
        stream_stats = run_monkeypatch(args)

    summaries = [s.summary() for s in stream_stats]
    agg = {
        'total_frames': sum(s['frames'] for s in summaries),
        'aggregate_fps': sum(s['frames'] for s in summaries) / max(1e-9, sum(s['duration_sec'] for s in summaries)/len(summaries)),
        'avg_latency_ms': statistics.mean([s['latency_avg_ms'] for s in summaries]) if summaries else 0.0,
        'p95_latency_ms': statistics.mean([s['latency_p95_ms'] for s in summaries]) if summaries else 0.0,
        'max_latency_ms': max([s['latency_max_ms'] for s in summaries]) if summaries else 0.0,
        'avg_vision_score': statistics.mean([s['vision_score_avg'] for s in summaries]) if summaries else 0.0,
    }
    metrics = collect_system_metrics()
    result = {
        'mode': args.mode,
        'streams': args.streams,
        'frame_spec': {'width': args.width, 'height': args.height},
        'per_stream': summaries,
        'aggregate': agg,
        'system_metrics': metrics,
    }

    print("\n=== Load Test Summary ===")
    print(json.dumps(result, indent=2))

    if args.stats_file:
        try:
            with open(args.stats_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            print(f"Saved stats to {args.stats_file}")
        except Exception as e:
            print(f"Failed to save stats file: {e}")

if __name__ == '__main__':
    main()
