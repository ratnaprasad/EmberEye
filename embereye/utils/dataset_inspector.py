from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DatasetInspector:
    """
    Inspect YOLO-style datasets under a base directory.
    Expects the structure:
      base_dir/
        dataset/
          images/{train,val,test}
          labels/{train,val,test}
    Labels are expected in YOLO txt format per image.
    """

    def __init__(self, base_dir: str = "./training_data") -> None:
        self.base_dir = Path(base_dir)
        self.dataset_dir = self.base_dir / "dataset"
        self.images = {
            'train': self.dataset_dir / 'images' / 'train',
            'val': self.dataset_dir / 'images' / 'val',
            'test': self.dataset_dir / 'images' / 'test',
        }
        self.labels = {
            'train': self.dataset_dir / 'labels' / 'train',
            'val': self.dataset_dir / 'labels' / 'val',
            'test': self.dataset_dir / 'labels' / 'test',
        }

    def exists(self) -> bool:
        return self.dataset_dir.exists()

    def split_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for split, p in self.images.items():
            counts[split] = len(list(p.glob("*.*"))) if p.exists() else 0
        return counts

    def label_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for split, p in self.labels.items():
            counts[split] = len(list(p.glob("*.txt"))) if p.exists() else 0
        return counts

    def class_distribution(self, class_names: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Aggregate class counts across all splits by parsing YOLO label files.
        If class_names are provided, map indices to names; otherwise use indices as keys.
        """
        dist: Dict[str, int] = {}
        # Use names mapping if provided
        def key_for(idx: int) -> str:
            if class_names and 0 <= idx < len(class_names):
                return class_names[idx]
            return str(idx)

        for split_dir in self.labels.values():
            if not split_dir.exists():
                continue
            for lf in split_dir.glob('*.txt'):
                try:
                    with open(lf, 'r') as f:
                        for line in f:
                            parts = line.strip().split()
                            if not parts:
                                continue
                            cls = int(float(parts[0]))
                            k = key_for(cls)
                            dist[k] = dist.get(k, 0) + 1
                except Exception:
                    # Skip unreadable/malformed files silently for robustness
                    continue
        return dist

    def summary(self, class_names: Optional[List[str]] = None) -> Dict[str, object]:
        return {
            'images': self.split_counts(),
            'labels': self.label_counts(),
            'classes': self.class_distribution(class_names),
            'root': str(self.dataset_dir),
        }
