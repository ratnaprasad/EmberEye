"""
Test PyTorch CUDA availability as it would be loaded by EmberEye Studio
This simulates the environment when launching Studio without activated venv
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("EmberEye Studio - PyTorch CUDA Test")
print("=" * 60)
print()

# Setup DLL paths (same as main.py)
try:
    venv_path = Path(sys.executable).parent.parent
    torch_lib_path = venv_path / "Lib" / "site-packages" / "torch" / "lib"
    
    print(f"Virtual environment: {venv_path}")
    print(f"Torch lib path: {torch_lib_path}")
    print(f"Torch lib exists: {torch_lib_path.exists()}")
    print()
    
    if torch_lib_path.exists():
        torch_lib_str = str(torch_lib_path)
        
        # Add to PATH
        if torch_lib_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")
            print(f"✓ Added torch lib to PATH")
        
        # Windows-specific: Add DLL directory
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(torch_lib_str)
                print(f"✓ Added torch lib as DLL directory")
            except Exception as e:
                print(f"✗ Could not add DLL directory: {e}")
    print()
except Exception as e:
    print(f"✗ Error setting up torch paths: {e}")
    print()

# Now try to import torch
print("Attempting to import torch...")
try:
    import torch
    print("✓ torch imported successfully!")
    print()
    
    print("PyTorch Information:")
    print(f"  Version: {torch.__version__}")
    print(f"  CUDA compiled: {torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A'}")
    print()
    
    print("Checking CUDA availability...")
    cuda_available = torch.cuda.is_available()
    print(f"  CUDA available: {cuda_available}")
    
    if cuda_available:
        print(f"  GPU count: {torch.cuda.device_count()}")
        print(f"  GPU name: {torch.cuda.get_device_name(0)}")
        
        # Check compute capability
        cap = torch.cuda.get_device_capability(0)
        cap_str = f"sm_{cap[0]}{cap[1]}"
        print(f"  GPU capability: {cap_str}")
        
        # Check if supported
        supported = torch.cuda.get_arch_list()
        print(f"  Supported architectures: {', '.join(supported)}")
        
        is_supported = cap_str in supported
        print(f"  GPU supported: {is_supported}")
        
        if is_supported:
            print()
            print("=" * 60)
            print("SUCCESS! GPU will be used for training")
            print("=" * 60)
        else:
            print()
            print("=" * 60)
            print("WARNING: GPU not supported, will use CPU")
            print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("CUDA not available - will use CPU")
        print("=" * 60)
    
except Exception as e:
    print(f"✗ Failed to import torch: {e}")
    print()
    import traceback
    traceback.print_exc()
    print()
    print("=" * 60)
    print("ERROR: PyTorch CUDA setup failed")
    print("=" * 60)
    sys.exit(1)
