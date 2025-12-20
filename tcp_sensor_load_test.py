#!/usr/bin/env python3
"""
TCP Sensor Load Test for EmberEye

Simulates multiple concurrent TCP sensor clients sending locid, sensor readings,
and thermal frame packets to the EmberEye TCP server (default port 9001).

Usage Examples:
  python tcp_sensor_load_test.py --clients 5 --packets 100 --port 9001
  python tcp_sensor_load_test.py --clients 3 --duration 10 --rate 5 --port 9001
  python tcp_sensor_load_test.py --clients 2 --packets 50 --include-frames --stats-file results.json

Parameters:
  --clients N          Number of concurrent TCP clients (default 5)
  --packets N          Total packets per client to send (mutually exclusive with --duration)
  --duration SEC       Duration (seconds) to run instead of fixed packet count
  --rate PKT/SEC       Packets per second per client (default 10)
  --port PORT          TCP server port (default 9001)
  --host HOST          TCP server host (default 127.0.0.1)
  --include-frames     Send thermal frame packets in addition to sensor packets
  --locid-prefix STR   Location ID prefix (default 'room')
  --report-interval SEC    Progress report interval (default 2.0)
  --stats-file PATH    JSON output file with results
  --seed INT           RNG seed for reproducibility (default 42)

Packet Types Sent:
  1. #locid:<location>!               - Sets location ID for client
  2. #Sensor:ADC1=X,ADC2=Y,ADC3=Z!   - Gas sensor readings (random values)
  3. #frame:<hex_data>!               - Thermal frame 32x24 pixels (optional)

Outputs:
  - Per-client statistics: packets sent, latency, throughput
  - Aggregate metrics: total packets, avg/p95/max latency, system metrics
  - Optional JSON export for further analysis

Notes:
  - Creates persistent connections per client
  - Sends locid once at start, then alternates sensor/frame packets
  - Frame generation is synthetic (random hex values)
  - Measures send latency (time to socket.sendall)
  - Real processing latency visible in app logs (logs/tcp_debug.log)
"""
from __future__ import annotations
import argparse, time, threading, socket, random, json, statistics, sys
from typing import List, Dict

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None


def parse_args():
    p = argparse.ArgumentParser(description="EmberEye TCP sensor load tester")
    p.add_argument('--clients', type=int, default=5)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--packets', type=int, help='Packets per client')
    g.add_argument('--duration', type=float, help='Duration (seconds) to run')
    p.add_argument('--rate', type=float, default=10.0, help='Packets/sec per client')
    p.add_argument('--port', type=int, default=9001)
    p.add_argument('--host', type=str, default='127.0.0.1')
    p.add_argument('--include-frames', action='store_true')
    p.add_argument('--locid-prefix', type=str, default='room')
    p.add_argument('--report-interval', type=float, default=2.0)
    p.add_argument('--stats-file', type=str)
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()


class ClientStats:
    def __init__(self):
        self.packets_sent = 0
        self.bytes_sent = 0
        self.latencies: List[float] = []
        self.errors = 0
        self.start_time = time.time()

    def add(self, latency: float, byte_count: int):
        self.latencies.append(latency)
        self.packets_sent += 1
        self.bytes_sent += byte_count

    def summary(self) -> Dict:
        dur = time.time() - self.start_time
        return {
            'packets': self.packets_sent,
            'bytes': self.bytes_sent,
            'errors': self.errors,
            'duration_sec': dur,
            'pps': self.packets_sent / dur if dur > 0 else 0.0,
            'throughput_kbps': (self.bytes_sent / dur / 1024 * 8) if dur > 0 else 0.0,
            'latency_avg_ms': statistics.mean(self.latencies) * 1000 if self.latencies else 0.0,
            'latency_p95_ms': (statistics.quantiles(self.latencies, n=20)[18] * 1000) if len(self.latencies) >= 20 else 0.0,
            'latency_max_ms': max(self.latencies) * 1000 if self.latencies else 0.0,
        }


def generate_sensor_packet(client_id: int, rng: random.Random) -> str:
    """Generate #Sensor:ADC1=X,ADC2=Y,ADC3=Z! packet with random values"""
    adc1 = rng.randint(400, 700)
    adc2 = rng.randint(750, 900)
    adc3 = rng.randint(850, 950)
    return f"#Sensor:ADC1={adc1},ADC2={adc2},ADC3={adc3}!\n"


def generate_frame_packet(client_id: int, rng: random.Random) -> str:
    """Generate #frame:<hex_data>! packet with 32x24 pixels (3072 hex chars)"""
    # Each pixel is 2 bytes = 4 hex chars
    # Total: 768 pixels * 4 chars = 3072 chars
    hex_data = ''.join(f"{rng.randint(0, 65535):04X}" for _ in range(768))
    return f"#frame:{hex_data}!\n"


def tcp_client_worker(client_id: int, args, stats: ClientStats):
    """Worker thread simulating a single TCP sensor client"""
    rng = random.Random(args.seed + client_id)
    loc_id = f"{args.locid_prefix}_{client_id}"
    
    try:
        # Connect to server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.host, args.port))
        
        # Send locid packet once at start
        locid_pkt = f"#locid:{loc_id}!\n"
        t0 = time.perf_counter()
        sock.sendall(locid_pkt.encode('utf-8'))
        stats.add(time.perf_counter() - t0, len(locid_pkt))
        
        # Calculate packet sending parameters
        packet_interval = 1.0 / args.rate if args.rate > 0 else 0
        stop_time = time.time() + args.duration if args.duration else None
        target_packets = args.packets if args.packets else float('inf')
        
        next_send = time.time()
        packet_count = 1  # Already sent locid
        
        while True:
            if stop_time and time.time() >= stop_time:
                break
            if packet_count >= target_packets:
                break
            
            # Pace sending
            now = time.time()
            if packet_interval > 0 and now < next_send:
                time.sleep(max(0, next_send - now))
            next_send = time.time() + packet_interval
            
            # Alternate between sensor and frame packets
            if args.include_frames and packet_count % 2 == 0:
                packet = generate_frame_packet(client_id, rng)
            else:
                packet = generate_sensor_packet(client_id, rng)
            
            t0 = time.perf_counter()
            sock.sendall(packet.encode('utf-8'))
            latency = time.perf_counter() - t0
            stats.add(latency, len(packet))
            packet_count += 1
        
        sock.close()
        
    except Exception as e:
        stats.errors += 1
        print(f"Client {client_id} error: {e}")


def run_load_test(args):
    """Main orchestrator for TCP load test"""
    client_stats: List[ClientStats] = [ClientStats() for _ in range(args.clients)]
    
    threads = [
        threading.Thread(target=tcp_client_worker, args=(i, args, client_stats[i]), daemon=True)
        for i in range(args.clients)
    ]
    
    print(f"Starting {args.clients} TCP clients connecting to {args.host}:{args.port}")
    for t in threads:
        t.start()
    
    # Progress reporting
    last_report = time.time()
    while any(t.is_alive() for t in threads):
        time.sleep(0.25)
        if time.time() - last_report >= args.report_interval:
            last_report = time.time()
            total_pkts = sum(s.packets_sent for s in client_stats)
            dur = time.time() - min(s.start_time for s in client_stats)
            agg_pps = total_pkts / max(1e-9, dur)
            print(f"[progress] total_packets={total_pkts} agg_pps={agg_pps:.1f}")
    
    for t in threads:
        t.join()
    
    return client_stats


def collect_system_metrics():
    if not psutil:
        return {}
    import os
    p = psutil.Process(os.getpid())
    with p.oneshot():
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.2),
            'mem_rss_mb': p.memory_info().rss / (1024 * 1024),
            'mem_percent': p.memory_percent(),
            'threads': p.num_threads()
        }


def main():
    args = parse_args()
    
    print(f"TCP Load Test Configuration:")
    print(f"  Clients: {args.clients}")
    print(f"  Target: {args.packets} packets" if args.packets else f"  Duration: {args.duration}s")
    print(f"  Rate: {args.rate} pkt/sec/client")
    print(f"  Frames: {'YES' if args.include_frames else 'NO'}")
    print()
    
    client_stats = run_load_test(args)
    
    summaries = [s.summary() for s in client_stats]
    agg = {
        'total_packets': sum(s['packets'] for s in summaries),
        'total_bytes': sum(s['bytes'] for s in summaries),
        'total_errors': sum(s['errors'] for s in summaries),
        'aggregate_pps': sum(s['packets'] for s in summaries) / max(1e-9, sum(s['duration_sec'] for s in summaries) / len(summaries)),
        'avg_latency_ms': statistics.mean([s['latency_avg_ms'] for s in summaries]) if summaries else 0.0,
        'p95_latency_ms': statistics.mean([s['latency_p95_ms'] for s in summaries]) if summaries else 0.0,
        'max_latency_ms': max([s['latency_max_ms'] for s in summaries]) if summaries else 0.0,
    }
    
    metrics = collect_system_metrics()
    
    result = {
        'test_config': {
            'clients': args.clients,
            'target': f"{args.packets} packets" if args.packets else f"{args.duration}s duration",
            'rate_pps': args.rate,
            'include_frames': args.include_frames,
            'server': f"{args.host}:{args.port}",
        },
        'per_client': summaries,
        'aggregate': agg,
        'system_metrics': metrics,
    }
    
    print("\n=== TCP Load Test Summary ===")
    print(json.dumps(result, indent=2))
    
    if args.stats_file:
        try:
            with open(args.stats_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
            print(f"\nSaved stats to {args.stats_file}")
        except Exception as e:
            print(f"Failed to save stats file: {e}")


if __name__ == '__main__':
    main()
