"""Thermal calibration helper.

Usage:
    python calibrate_thermal.py --reference 26.4 --samples 20 --port 4888 --loc-id cam01

Workflow:
1. Collect N frames from simulator or real sensor.
2. Compute average raw value (pre-calibration) across all pixels.
3. Solve linear mapping raw * scale + offset = reference_temp.
   If you also supply a second known point (e.g. hot object), script can fit scale more accurately.
4. Writes updated thermal_calibration into stream_config.json.

For now with one reference point we set scale to 0.01 (default) and adjust offset so that mean maps to reference.
You can later refine scale by providing --hot-ref <temp> while placing a known hot source; then we fit both scale and offset.
"""
import json, os, argparse, time, socket
from statistics import mean

STREAM_CFG = os.path.join(os.path.dirname(__file__), 'stream_config.json')

def read_config():
    with open(STREAM_CFG, 'r') as f:
        return json.load(f)

def write_config(cfg):
    with open(STREAM_CFG, 'w') as f:
        json.dump(cfg, f, indent=4)

def collect_frames(host, port, samples):
    raw_frames = []
    buf = ''
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.settimeout(5)
    start = time.time()
    try:
        while len(raw_frames) < samples and time.time() - start < 60:
            data = s.recv(8192)
            if not data:
                break
            buf += data.decode('utf-8', errors='ignore')
            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                line = line.strip()
                if line.startswith('#frame') and line.endswith('!'):
                    # Extract hex payload after first ':'
                    try:
                        payload = line.split(':',1)[1].rstrip('!').strip()
                        payload = payload.replace(' ', '')
                        if len(payload) == 3336:  # full frame
                            raw_frames.append(payload[:3072])  # grid portion only
                            print(f"Captured frame {len(raw_frames)}")
                            if len(raw_frames) >= samples:
                                break
                    except Exception:
                        pass
        return raw_frames
    finally:
        s.close()

def average_raw_value(grid_hex):
    # grid_hex length 3072; each pixel 4 chars
    values = [int(grid_hex[i:i+4], 16) for i in range(0, len(grid_hex), 4)]
    return mean(values)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=4888)
    ap.add_argument('--samples', type=int, default=10)
    ap.add_argument('--reference', type=float, required=True, help='Known ambient temperature (C)')
    ap.add_argument('--hot-ref', type=float, help='Optional known hot source temperature (C) for scale fitting')
    args = ap.parse_args()

    frames = collect_frames(args.host, args.port, args.samples)
    if not frames:
        print('No frames captured.')
        return

    avg_raw = mean(average_raw_value(f) for f in frames)
    print(f"Average raw value (unsigned): {avg_raw:.2f}")

    cfg = read_config()
    calib = cfg.get('thermal_calibration', {})

    if args.hot_ref:
        # Need second measurement: pick max pixel from last frame as hot candidate
        last_vals = [int(frames[-1][i:i+4], 16) for i in range(0, len(frames[-1]), 4)]
        hot_raw = max(last_vals)
        # Solve linear system:
        # reference = avg_raw * scale + offset
        # hot_ref  = hot_raw * scale + offset
        # => scale = (hot_ref - reference)/(hot_raw - avg_raw)
        scale = (args.hot_ref - args.reference)/(hot_raw - avg_raw)
        offset = args.reference - avg_raw * scale
        print(f"Fitted scale={scale:.6f} offset={offset:.3f} (hot_raw={hot_raw})")
    else:
        # Keep scale, adjust offset only
        scale = calib.get('scale', 0.01)
        offset = args.reference - avg_raw * scale
        print(f"Adjusted offset={offset:.3f} using existing scale={scale:.6f}")

    calib.update({'signed': False, 'scale': scale, 'offset': offset})
    cfg['thermal_calibration'] = calib
    write_config(cfg)
    print('Updated stream_config.json with new calibration.')

if __name__ == '__main__':
    main()
