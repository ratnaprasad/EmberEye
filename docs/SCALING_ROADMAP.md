# EmberEye Scaling Roadmap (100 Cameras + 100 PF Devices)

## Phase 0 – Stabilization (Week 1)
Goals: Eliminate crashes; validate async vision + TCP marshaling
- Implement Qt signal marshaling (DONE)
- Async vision detection pool (DONE)
- Optional asyncio TCP server skeleton (DONE)
- Run soak: 5 cameras @ 25 FPS + 5 sensors @ 10 Hz (2h)
- Success Criteria: No segfaults; <5% dropped frames; sensor latency P95 < 25 ms

## Phase 1 – Parallelism & Backpressure (Week 2)
Goals: Improve ingestion concurrency; add metrics & backpressure
- Add frame rate adaptation (drop to 15 FPS on queue congestion)
- Add packet queue depth metrics & Prometheus endpoint
- Implement hot path logging queue (async flush) for TCP
- Soak test: 10 cameras + 20 sensors (2h)
- Success Criteria: CPU < 70%; Latency P95 stable; zero crash

## Phase 2 – Async & Batching Expansion (Weeks 3–4)
Goals: Scale to 30 cameras + 40 sensors
- Convert threaded TCP server callers fully to asyncio variant (config switch default)
- Packet batching (aggregate sensor readings per 100 ms window)
- Thermal frame compression (RLE or delta) before fusion
- Vision ROI cropping to reduce per-frame cost
- Success Criteria: 30 cameras @ ≥15 FPS; Sensor PPS ≥ 400; Memory < 1.2 GB

## Phase 3 – Multiprocessing & Event Bus (Weeks 5–6)
Goals: Reach 60 cameras + 60 sensors
- Split camera capture into N processes (10 cameras each)
- Introduce Redis / NATS event bus for inter-process frame metadata & sensor events
- Central fusion aggregator process
- Success Criteria: Dropped frame ratio < 5%; Alert latency < 120 ms; CPU headroom ≥ 20%

## Phase 4 – Optimization & Compression (Weeks 7–8)
Goals: 80 cameras + 80 sensors
- Frame downscaling (e.g., 640x480 → 320x240) with dynamic upscale for alarms
- Introduce GPU pathway for heavy detection (optional YOLO/TensorRT)
- Implement baseline anomaly cache to short-circuit unchanged scenes
- Success Criteria: Aggregate FPS ≥ 1200 (15 FPS × 80); Sensor PPS ≥ 800 stable

## Phase 5 – Target Scale Validation (Weeks 9+)
Goals: 100 cameras + 100 sensors
- Horizontal scale across 2 nodes (50/50 split) with load balancer
- Distributed alert deduplication (time-window merge)
- Full resilience tests (process kill, network partitions)
- Success Criteria: Recovery < 30 s after failure; Alert accuracy maintained; Resource usage balanced

## Continuous Validation
Each phase ends with:
- Soak test (2h) & stress test (10 min burst)
- Metrics snapshot stored (CPU, Mem, Latency, PPS/FPS)
- Report diff vs previous phase

## Key Metrics Thresholds (Targets)
- Vision detection P95 latency: < 10 ms (heuristic), < 40 ms (deep model)
- Sensor processing P95 latency: < 25 ms
- Alert end-to-end P95 latency: < 150 ms
- Dropped frames: < 5% per camera
- Packet loss: < 0.5% sensors

## Exit Criteria for 100/100
- Stable 24h soak with all components
- No memory leak (>10% growth)
- Automatic recovery verified (process restart / network reconnection)
- Documentation updated (runbook + scaling guide)
