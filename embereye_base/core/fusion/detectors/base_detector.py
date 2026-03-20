from abc import ABC, abstractmethod
from typing import Optional, Any

from ..fusion_engine import Detection


class BaseDetector(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.last_detection: Optional[Detection] = None

    @abstractmethod
    def detect(self, data: Any) -> Optional[Detection]:
        raise NotImplementedError

    @abstractmethod
    def get_thresholds(self) -> dict:
        raise NotImplementedError

    def update_config(self, config: dict) -> None:
        self.config = config
