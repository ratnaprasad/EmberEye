from dataclasses import dataclass


@dataclass
class HybridDetectionConfig:
    """Centralized configuration for hybrid detection and rule gating."""

    # Hybrid queueing / detector thresholds
    heuristic_threshold: float = 0.20
    force_yolo_every_n_frames: int = 10
    yolo_conf_threshold: float = 0.05
    possible_conf_threshold: float = 0.6
    confirmed_conf_threshold: float = 0.8

    # Rule alarm gating
    rule_min_yolo_conf: float = 0.6
    rule_min_fusion_conf: float = 0.3

    @classmethod
    def from_dict(cls, data: dict):
        """Create config from dictionary (e.g., from saved settings)."""
        if not isinstance(data, dict):
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


hybrid_detection_config = HybridDetectionConfig()
