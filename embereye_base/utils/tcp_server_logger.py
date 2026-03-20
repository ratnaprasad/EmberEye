"""TCP server logger - dedicated logging for TCP server events."""
import os
import logging
from logging.handlers import RotatingFileHandler

# Create logs directory
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# TCP server logger
tcp_logger = logging.getLogger('tcp_async_server')
tcp_logger.setLevel(logging.DEBUG)
tcp_logger.propagate = False

# Clear existing handlers
tcp_logger.handlers.clear()

# Debug log
debug_handler = RotatingFileHandler(
    os.path.join(log_dir, 'tcp_server_debug.log'),
    maxBytes=10*1024*1024,
    backupCount=3
)
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
debug_handler.setFormatter(debug_formatter)
tcp_logger.addHandler(debug_handler)

# Error log
error_handler = RotatingFileHandler(
    os.path.join(log_dir, 'tcp_server_error.log'),
    maxBytes=5*1024*1024,
    backupCount=2
)
error_handler.setLevel(logging.WARNING)
error_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
error_handler.setFormatter(error_formatter)
tcp_logger.addHandler(error_handler)

def log_info(message: str):
    """Log info event."""
    tcp_logger.info(message)

def log_debug(message: str):
    """Log debug information."""
    tcp_logger.debug(message)

def log_warning(message: str):
    """Log warning."""
    tcp_logger.warning(message)

def log_error(message: str):
    """Log error."""
    tcp_logger.error(message)
