"""Vision detection logger - separate logging for vision/YOLO detection events."""
import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Create logs directory if not exists
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Vision detection logger
vision_logger = logging.getLogger('vision_detector')
vision_logger.setLevel(logging.DEBUG)
vision_logger.propagate = False  # Don't propagate to root logger

# Clear existing handlers
vision_logger.handlers.clear()

# Debug log file (detailed detection info)
debug_handler = RotatingFileHandler(
    os.path.join(log_dir, 'vision_debug.log'),
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=3
)
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
debug_handler.setFormatter(debug_formatter)
vision_logger.addHandler(debug_handler)

# Error log file (warnings and errors only)
error_handler = RotatingFileHandler(
    os.path.join(log_dir, 'vision_error.log'),
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=2
)
error_handler.setLevel(logging.WARNING)
error_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
error_handler.setFormatter(error_formatter)
vision_logger.addHandler(error_handler)

def log_detection(message: str):
    """Log detection event (info level)."""
    vision_logger.info(message)

def log_debug(message: str):
    """Log debug information."""
    vision_logger.debug(message)

def log_warning(message: str):
    """Log warning."""
    vision_logger.warning(message)

def log_error(message: str):
    """Log error."""
    vision_logger.error(message)
