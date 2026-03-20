# EmberEye Scaling Risks & Mitigations

| Risk | Description | Impact | Mitigation | Phase |
|------|-------------|--------|-----------|-------|
| Qt Thread Violations | Non-main thread creates/uses QObjects (timers, widgets) | Crash (segfault) | Strict signal marshaling; audit packet handlers | 0 |
| GIL Contention | 100 synchronous detections saturate Python threads | Throughput collapse | Move detection off main thread; use multiprocessing / native libs | 2–3 |
| Packet Storm Overload | Sensor burst floods processing path | Latency spikes, dropped packets | Async queue + batch window + backpressure (drop oldest) | 2 |
| Logging I/O Blocking | High-frequency sync file writes | CPU stalls, jitter | Buffered queue writer + rotation + compression | 1 |
| Memory Growth | Frame buffers accumulate without release | OOM / swap | Downscale frames, reuse preallocated buffers, periodic audits | 3–4 |
| Fusion Hot Path Complexity | Fusion logic expands with more sensors | Increased latency | Profile & cache derived values; incremental fusion updates | 3 |
| Network Instability | Camera RTSP reconnect storms | Resource drain | Exponential backoff, staggered reconnect scheduler | 1–2 |
| Alert Flooding | Repeated similar events across cameras | Operator fatigue | Debounce & correlation window, severity aggregation | 4–5 |
| Baseline Drift | Environmental changes degrade detection | False alarms / misses | Scheduled baseline revalidation & candidate review queue | Continuous |
| Single Point of Failure | Monolithic process handling all streams | Total outage | Split ingestion/process/UI; supervisor restarts | 3–5 |
| Time Sync Variance | Different devices unsynchronized | Fusion inaccuracies | NTP sync check; timestamp normalization | 2 |
| Security Exposure | Open TCP port unauthenticated | Unauthorized access | Optional auth token per packet; IP allowlist | 1–2 |
| Config Drift | Multi-node inconsistent thresholds | Unpredictable alerts | Central config service & versioned rollout | 5 |
| Resource Starvation | Competing workloads (GPU/CPU share) | Latency spikes | Classify workloads, allocate process affinity / cgroups | 4–5 |
| Data Retention Bloat | Logs & raw frames accumulate | Storage exhaustion | Retention policy + compaction + S3/archive | 3–5 |

## Mitigation Details
- Backpressure: Drop oldest non-critical packets when queue > 80% to preserve recent state.
- Metrics: Export Prometheus counters (frame_processed_total, sensor_packets_total, queue_depth, dropped_frames_total) early.
- Process Supervision: Use systemd / launchd or Docker health checks for auto-restart.
- Configuration Safety: Schema validation before applying new thresholds; rollback on anomaly spike.

## Monitoring Triggers
- Queue depth > 70% for >30s → reduce camera FPS by 25%.
- Dropped frames >5% over 5m window → scale out ingestion process.
- Alert rate > baseline × 3 → enable debounce layer.

## Audit & Review Cadence
- Weekly: Memory usage trend & top allocations.
- Bi-weekly: Detection accuracy validation set.
- Monthly: Security port scan & dependency CVE check.
