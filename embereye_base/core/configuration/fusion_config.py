from dataclasses import dataclass


@dataclass
class FusionConfig:
    """Centralized configuration for sensor fusion and alarm presentation."""

    # Sensor thresholds
    smoke_threshold_pct: float = 25.0
    flame_threshold_pct: float = 25.0
    gas_ppm_threshold: float = 400.0

    # Thermal thresholds
    temp_threshold: float = 40.0
    critical_temp_threshold: float = 60.0

    # Vision thresholds used by fusion
    vision_threshold: float = 0.7

    # Fusion weights
    vision_confidence_weight: float = 0.5

    # Behavior settings
    freeze_on_alarm: bool = True
    show_fusion_overlay: bool = True
    hot_cell_decay_time: int = 5

    @classmethod
    def from_dict(cls, data: dict):
        """Create config from dictionary (e.g., from saved settings)."""
        if not isinstance(data, dict):
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


fusion_config = FusionConfig()
