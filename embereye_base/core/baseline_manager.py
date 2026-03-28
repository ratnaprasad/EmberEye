import numpy as np
import time
import json
import os

# Default data directory: embereye_base/config/ (alongside committed baselines_events.json sample)
_DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')


class BaselineManager:
    def __init__(self):
        self.baselines = {}  # loc_id -> baseline frame (np.array)
        self.candidates = {}  # loc_id -> {'frame': np.array, 'timestamp': float}
        self.change_threshold = 0.15  # normalized diff threshold
        self.persistence_seconds = 10  # seconds a change must persist
        self.event_log = []

    def update(self, loc_id, frame):
        frame = frame.astype(np.float32)
        baseline = self.baselines.get(loc_id)
        now = time.time()
        if baseline is None:
            self.baselines[loc_id] = frame.copy()
            return None
        diff = np.abs(frame - baseline) / 255.0
        mean_diff = np.mean(diff)
        if mean_diff > self.change_threshold:
            cand = self.candidates.get(loc_id)
            if cand:
                if now - cand['timestamp'] >= self.persistence_seconds:
                    self.event_log.append({'loc_id': loc_id, 'frame': frame, 'timestamp': now, 'type': 'candidate'})
                    return {'loc_id': loc_id, 'frame': frame, 'timestamp': now}
            else:
                self._add_candidate(loc_id, frame, now)
        else:
            if loc_id in self.candidates:
                del self.candidates[loc_id]
        return None

    def _add_candidate(self, loc_id, frame, timestamp):
        self.candidates[loc_id] = {'frame': frame, 'timestamp': timestamp}

    def approve_candidate(self, loc_id):
        cand = self.candidates.get(loc_id)
        if cand:
            self.baselines[loc_id] = cand['frame'].copy()
            self.event_log.append({'loc_id': loc_id, 'frame': cand['frame'], 'timestamp': time.time(), 'type': 'approved'})
            del self.candidates[loc_id]
            return True
        return False

    def get_event_log(self):
        return self.event_log

    def save_to_disk(self, path_prefix=None):
        if path_prefix is None:
            path_prefix = os.path.join(_DEFAULT_DATA_DIR, 'baselines')
        os.makedirs(os.path.dirname(path_prefix) if os.path.dirname(path_prefix) else '.', exist_ok=True)
        # Save baselines
        for loc_id, arr in self.baselines.items():
            np.save(f'{path_prefix}_{loc_id}.npy', arr)
        # Save event log
        with open(f'{path_prefix}_events.json', 'w') as f:
            json.dump(self.event_log, f, default=lambda o: o.tolist() if isinstance(o, np.ndarray) else o)

    def load_from_disk(self, path_prefix=None):
        if path_prefix is None:
            path_prefix = os.path.join(_DEFAULT_DATA_DIR, 'baselines')
        data_dir = os.path.dirname(path_prefix) or '.'
        prefix_base = os.path.basename(path_prefix)
        # Load baselines
        if os.path.isdir(data_dir):
            for fname in os.listdir(data_dir):
                if fname.startswith(prefix_base) and fname.endswith('.npy'):
                    loc_id = fname[len(prefix_base)+1:-4]
                    self.baselines[loc_id] = np.load(os.path.join(data_dir, fname))
        # Load events
        events_path = f'{path_prefix}_events.json'
        if os.path.exists(events_path):
            with open(events_path, 'r') as f:
                self.event_log = json.load(f)

