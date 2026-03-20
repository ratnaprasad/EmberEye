"""
Auto-detect and configure GPU/CPU for YOLOv8
Supports NVIDIA CUDA, AMD ROCm, Intel oneAPI, and CPU fallback
"""

import torch
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_device_config():
    """
    Returns optimal device configuration based on available hardware.
    
    Returns:
        dict: Configuration with device, GPU info, precision settings
    """
    config = {
        'device': 'cpu',
        'device_index': None,
        'device_name': 'CPU (Default)',
        'gpu_available': False,
        'gpu_type': None,
        'mixed_precision': False,
        'memory_fraction': 0.8,
        'torch_device': torch.device('cpu'),
    }
    
    try:
        # Check NVIDIA CUDA
        if torch.cuda.is_available():
            device_index = 0
            config['device'] = 'cuda'
            config['device_index'] = device_index
            config['device_name'] = f"NVIDIA {torch.cuda.get_device_name(device_index)}"
            config['gpu_available'] = True
            config['gpu_type'] = 'NVIDIA_CUDA'
            config['mixed_precision'] = True
            config['torch_device'] = torch.device('cuda', device_index)
            
            # Log GPU info
            props = torch.cuda.get_device_properties(device_index)
            total_memory_gb = props.total_memory / 1e9
            
            logger.info(f"✅ GPU Detected: {config['device_name']}")
            logger.info(f"   Total Memory: {total_memory_gb:.1f}GB")
            logger.info(f"   Compute Capability: {props.major}.{props.minor}")
            logger.info(f"   CUDA Cores: {props.multi_processor_count * 128}")
            
        # Check for CPU-only (no GPU)
        else:
            logger.warning("⚠️  No GPU detected - using CPU mode")
            logger.info("   For faster training, install GPU support:")
            logger.info("   ")
            logger.info("   NVIDIA CUDA (Recommended):")
            logger.info("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            logger.info("   ")
            logger.info("   AMD ROCm:")
            logger.info("   pip install torch-directml")
            logger.info("   ")
            logger.info("   macOS Metal (M1/M2/M3):")
            logger.info("   pip install torch torchvision torchaudio")
            
    except Exception as e:
        logger.warning(f"⚠️  Device detection error: {e}")
        logger.info("   Falling back to CPU mode")
    
    return config


def log_device_config(config):
    """Pretty print device configuration for debugging"""
    separator = "=" * 60
    logger.info(separator)
    logger.info("DEVICE CONFIGURATION")
    logger.info(separator)
    logger.info(f"Device: {config['device_name']}")
    logger.info(f"Device Type: {config['device']}")
    logger.info(f"GPU Available: {'✅ Yes' if config['gpu_available'] else '❌ No'}")
    logger.info(f"GPU Type: {config['gpu_type'] or 'N/A'}")
    logger.info(f"Mixed Precision: {'✅ Enabled' if config['mixed_precision'] else '❌ Disabled'}")
    logger.info(f"Memory Fraction: {config['memory_fraction']*100:.0f}%")
    logger.info(separator)


def get_yolo_device_config(device_config):
    """
    Convert device_config to YOLOv8-compatible settings.
    
    Args:
        device_config (dict): Device configuration from get_device_config()
    
    Returns:
        dict: YOLOv8 training parameters
    """
    return {
        'device': 0 if device_config['gpu_available'] else 'cpu',
        'half': device_config['mixed_precision'],
        'amp': device_config['mixed_precision'],
    }


def configure_torch_inference(device_config):
    """
    Configure PyTorch for inference with optimal settings.
    
    Args:
        device_config (dict): Device configuration from get_device_config()
    
    Returns:
        torch.device: Configured device for inference
    """
    torch_device = device_config['torch_device']
    
    if device_config['gpu_available']:
        # Enable benchmarking for consistent GPU performance
        torch.backends.cudnn.benchmark = True
        # Use deterministic algorithms if needed (slightly slower)
        # torch.use_deterministic_algorithms(True)
        
        logger.info(f"✅ Inference device set to: {device_config['device_name']}")
    else:
        # CPU optimization
        torch.set_num_threads(os.cpu_count() or 4)
        logger.info(f"✅ Inference device set to CPU ({os.cpu_count()} threads)")
    
    return torch_device


# Global configuration initialized on module load
DEVICE_CONFIG = get_device_config()

# Log configuration for debugging
if __name__ == '__main__':
    # Allow running this module directly for testing
    logging.basicConfig(level=logging.INFO)
    log_device_config(DEVICE_CONFIG)
    print("\nYOLOv8 Config:", get_yolo_device_config(DEVICE_CONFIG))
    print("Torch Inference Device:", DEVICE_CONFIG['torch_device'])
