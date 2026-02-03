"""
EmberEye Studio - Labs Edition v1.0.0
Centralized training and model development hub

Main Modules:
- forgelab: YOLO training and model fine-tuning (Phoenix Cycle)
- aviary: Human-in-the-loop feedback and review interface (HawkEye Review)
- emberarchive: Dataset management and organization
- commandnest: Model deployment and orchestration
- ignissim: Simulation hub for testing
"""

from .database_manager import StudioDatabaseManager
from .studio_login import StudioLoginWindow
from .studio_main_window import StudioMainWindow

__version__ = "1.0.0"
__all__ = ['StudioDatabaseManager', 'StudioLoginWindow', 'StudioMainWindow']
