"""
Model Export & Deployment System for EmberEye
Handles exporting trained models from training location to multiple deployment locations.
Supports cross-platform (CPU/GPU/MPS) client installations.
"""

import os
import json
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DeploymentProfile:
    """Profile for different deployment scenarios."""
    name: str  # "production_cpu", "production_gpu", "edge_device"
    device_type: str  # "cpu", "gpu", "mps"
    supported_os: List[str]  # ["windows", "macos", "linux"]
    optimization: str  # "speed", "accuracy", "balanced"
    quantization: bool = False  # Use quantized model for edge
    onnx_export: bool = False  # Export to ONNX for cross-platform


class ModelExporter:
    """Export trained models with metadata and device-specific optimizations."""
    
    def __init__(self, models_dir: str = "./models/yolo_versions"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir = self.models_dir / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)
    
    def export_trained_model(
        self,
        version: str,  # e.g., "v1", "v2"
        deployment_profiles: Optional[List[DeploymentProfile]] = None
    ) -> Tuple[bool, str]:
        """
        Export trained model with device-specific variants.
        
        Creates:
        - EmberEye.pt (CPU optimized)
        - EmberEye_gpu.pt (GPU optimized)
        - EmberEye_mps.pt (Apple optimized)
        
        Args:
            version: Model version to export (e.g., "v1")
            deployment_profiles: Custom deployment profiles
        
        Returns:
            (success: bool, message: str)
        """
        try:
            version_dir = self.models_dir / version
            if not version_dir.exists():
                return False, f"Model version {version} not found!"
            
            source_weights = version_dir / "weights" / "best.pt"
            if not source_weights.exists():
                return False, f"Model weights not found at {source_weights}"
            
            metadata_path = version_dir / "metadata.json"
            if not metadata_path.exists():
                return False, f"Model metadata not found at {metadata_path}"
            
            # Load metadata
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Create export directory
            export_dir = self.exports_dir / version
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # Use default profiles if not provided
            if deployment_profiles is None:
                deployment_profiles = self._get_default_profiles()
            
            logger.info(f"📦 Exporting {version} with {len(deployment_profiles)} deployment profiles...")
            
            # Create device-specific variants
            for profile in deployment_profiles:
                success, msg = self._create_device_variant(
                    source_weights=source_weights,
                    export_dir=export_dir,
                    profile=profile,
                    metadata=metadata,
                    version=version
                )
                if not success:
                    logger.warning(f"Warning creating {profile.name}: {msg}")
                else:
                    logger.info(f"✓ Created {profile.name} variant")
            
            # Create deployment manifest
            manifest = self._create_deployment_manifest(
                version=version,
                metadata=metadata,
                profiles=deployment_profiles,
                export_dir=export_dir
            )
            
            # Save manifest
            manifest_path = export_dir / "deployment_manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"✅ Export complete. Manifest saved to {manifest_path}")
            return True, f"Model {version} exported successfully with {len(deployment_profiles)} profiles"
        
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False, f"Export error: {e}"
    
    def _create_device_variant(
        self,
        source_weights: Path,
        export_dir: Path,
        profile: DeploymentProfile,
        metadata: dict,
        version: str
    ) -> Tuple[bool, str]:
        """Create device-specific model variant."""
        try:
            # Map profile to model naming convention
            model_names = {
                'cpu': 'EmberEye.pt',
                'gpu': 'EmberEye_gpu.pt',
                'mps': 'EmberEye_mps.pt'
            }
            
            model_name = model_names.get(profile.device_type, f"EmberEye_{profile.device_type}.pt")
            output_path = export_dir / model_name
            
            # Copy base model
            shutil.copy(source_weights, output_path)
            
            # Create device-specific config
            config_filename = model_name.replace('.pt', '_config.json')
            config_path = export_dir / config_filename
            
            device_config = {
                'model_name': model_name,
                'device_type': profile.device_type,
                'supported_os': profile.supported_os,
                'optimization': profile.optimization,
                'quantization': profile.quantization,
                'onnx_available': profile.onnx_export,
                'version': version,
                'exported_at': datetime.now().isoformat(),
                'training_metadata': metadata
            }
            
            with open(config_path, 'w') as f:
                json.dump(device_config, f, indent=2)
            
            return True, f"Created {model_name}"
        
        except Exception as e:
            return False, str(e)
    
    def _create_deployment_manifest(
        self,
        version: str,
        metadata: dict,
        profiles: List[DeploymentProfile],
        export_dir: Path
    ) -> dict:
        """Create deployment manifest with all available models."""
        return {
            'version': version,
            'exported_at': datetime.now().isoformat(),
            'training_metadata': metadata,
            'deployment_profiles': [
                {
                    'name': p.name,
                    'device_type': p.device_type,
                    'model_file': {
                        'cpu': 'EmberEye.pt',
                        'gpu': 'EmberEye_gpu.pt',
                        'mps': 'EmberEye_mps.pt'
                    }.get(p.device_type),
                    'config_file': {
                        'cpu': 'EmberEye_config.json',
                        'gpu': 'EmberEye_gpu_config.json',
                        'mps': 'EmberEye_mps_config.json'
                    }.get(p.device_type),
                    'supported_os': p.supported_os,
                    'optimization': p.optimization,
                    'instructions': self._get_deployment_instructions(p.device_type)
                }
                for p in profiles
            ],
            'quick_start': {
                'auto_detect': 'EmberEye.pt (recommended - auto-selects CPU/GPU)',
                'cpu_only': 'EmberEye.pt',
                'gpu_nvidia': 'EmberEye_gpu.pt',
                'gpu_apple': 'EmberEye_mps.pt'
            }
        }
    
    def _get_default_profiles(self) -> List[DeploymentProfile]:
        """Get default deployment profiles."""
        return [
            DeploymentProfile(
                name="production_cpu",
                device_type="cpu",
                supported_os=["windows", "macos", "linux"],
                optimization="balanced",
                quantization=False
            ),
            DeploymentProfile(
                name="production_gpu_nvidia",
                device_type="gpu",
                supported_os=["windows", "linux"],
                optimization="speed",
                quantization=False
            ),
            DeploymentProfile(
                name="production_gpu_apple",
                device_type="mps",
                supported_os=["macos"],
                optimization="speed",
                quantization=False
            ),
        ]
    
    def _get_deployment_instructions(self, device_type: str) -> str:
        """Get deployment instructions for device type."""
        instructions = {
            'cpu': """
1. Copy EmberEye.pt to EmberEye installation folder
2. Set device='cpu' in configuration
3. Supports all platforms: Windows, macOS, Linux
4. Fallback option if GPU not available
            """,
            'gpu': """
1. Copy EmberEye_gpu.pt to EmberEye installation folder
2. Ensure NVIDIA CUDA is installed (CUDA 11.8+)
3. Set device='0' (or GPU index) in configuration
4. Faster inference on NVIDIA GPUs
            """,
            'mps': """
1. Copy EmberEye_mps.pt to EmberEye installation folder
2. macOS 12.3+ with Apple Silicon (M1/M2/M3) or Intel GPU
3. Set device='mps' in configuration
4. Native Apple GPU acceleration
            """
        }
        return instructions.get(device_type, "See deployment manifest for details")


class ModelDeployer:
    """Deploy models to remote EmberEye installations."""
    
    def __init__(self, export_dir: str = "./models/yolo_versions/exports"):
        self.export_dir = Path(export_dir)
    
    def create_deployment_package(
        self,
        version: str,
        target_os: str = "auto",
        device_type: str = "cpu"
    ) -> Tuple[bool, str]:
        """
        Create a deployment package (.zip) for easy distribution.
        
        Args:
            version: Model version to package (e.g., "v1", "v2")
            target_os: Target OS ("windows", "macos", "linux", "auto" for all)
            device_type: Device type to include ("cpu", "gpu", "mps", "all")
        
        Returns:
            (success: bool, package_path: str)
        """
        try:
            version_export_dir = self.export_dir / version
            if not version_export_dir.exists():
                return False, f"Export directory not found: {version_export_dir}"
            
            # Load manifest
            manifest_path = version_export_dir / "deployment_manifest.json"
            if not manifest_path.exists():
                return False, f"Manifest not found: {manifest_path}"
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Create package directory
            package_name = f"EmberEye_{version}_{target_os}_{device_type}"
            package_dir = self.export_dir / "packages" / package_name
            package_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"📦 Creating deployment package: {package_name}")
            
            # Copy files based on device type
            files_to_copy = []
            
            if device_type == "all":
                device_types = ["cpu", "gpu", "mps"]
            else:
                device_types = [device_type]
            
            for dt in device_types:
                model_map = {
                    'cpu': 'EmberEye.pt',
                    'gpu': 'EmberEye_gpu.pt',
                    'mps': 'EmberEye_mps.pt'
                }
                
                model_file = model_map.get(dt)
                if model_file:
                    src = version_export_dir / model_file
                    if src.exists():
                        files_to_copy.append(src)
                        config_file = model_file.replace('.pt', '_config.json')
                        config_src = version_export_dir / config_file
                        if config_src.exists():
                            files_to_copy.append(config_src)
            
            # Copy README and manifest
            files_to_copy.append(manifest_path)
            
            # Create README
            readme_content = self._create_readme(manifest, device_type)
            readme_path = package_dir / "README.md"
            with open(readme_path, 'w') as f:
                f.write(readme_content)
            files_to_copy.append(readme_path)
            
            # Copy all files
            for src in files_to_copy:
                if src.exists():
                    shutil.copy(src, package_dir / src.name)
            
            # Create zip archive
            zip_path = self.export_dir / "packages" / f"{package_name}.zip"
            shutil.make_archive(
                str(zip_path.with_suffix('')),
                'zip',
                package_dir.parent,
                package_dir.name
            )
            
            logger.info(f"✅ Package created: {zip_path}")
            return True, str(zip_path)
        
        except Exception as e:
            logger.error(f"Package creation failed: {e}")
            return False, str(e)
    
    def _create_readme(self, manifest: dict, device_type: str) -> str:
        """Create README for deployment package."""
        profiles = {p['device_type']: p for p in manifest['deployment_profiles']}
        
        readme = """# EmberEye Model Deployment Package

## Overview
This package contains trained YOLOv8 model weights for EmberEye fire detection system.

## Package Contents
- EmberEye*.pt - Model weights (device-specific variants)
- EmberEye*_config.json - Configuration for each device type
- deployment_manifest.json - Complete deployment information

## Installation Steps

### Step 1: Locate EmberEye Installation
- Windows: `C:\\Program Files\\EmberEye\\`
- macOS: `/Applications/EmberEye/`
- Linux: `/opt/embereye/`

### Step 2: Backup Current Model
```bash
cp models/EmberEye.pt models/EmberEye.pt.backup
```

### Step 3: Copy New Model
- Extract this package
- Copy EmberEye*.pt to `<installation>/models/`
- Copy EmberEye*_config.json to `<installation>/models/`

### Step 4: Restart EmberEye
Close and reopen EmberEye application. It will auto-detect the new model.

## Quick Selection Guide

"""
        
        if device_type == "all":
            readme += """
### CPU-Only (EmberEye.pt)
✓ All platforms (Windows, macOS, Linux)
✓ Works on any machine
✗ Slower inference

### NVIDIA GPU (EmberEye_gpu.pt)
✓ Requires NVIDIA CUDA 11.8+
✓ 5-10x faster inference
✓ Windows, Linux

### Apple GPU (EmberEye_mps.pt)
✓ Requires macOS 12.3+
✓ M1/M2/M3 or Intel GPU
✓ 2-3x faster inference
"""
        
        readme += f"""

## Training Information
- Version: {manifest['version']}
- Trained Images: {manifest['training_metadata'].get('training_images', 'N/A')}
- Accuracy (mAP50): {manifest['training_metadata'].get('best_accuracy', 'N/A')}
- Loss: {manifest['training_metadata'].get('loss', 'N/A')}
- Exported: {manifest['exported_at']}

## Troubleshooting

### Model not loading?
1. Check EmberEye installation folder exists
2. Verify model file is in `models/` directory
3. Check log files for errors

### Slow inference?
1. Ensure correct device model is installed
2. For GPU: verify CUDA/Metal is properly installed
3. Check system resources (CPU/Memory)

### Rolling Back?
If performance degrades, restore backup:
```bash
rm models/EmberEye.pt
cp models/EmberEye.pt.backup models/EmberEye.pt
```

## Support
For issues, check:
- EmberEye logs in `logs/` directory
- Configuration in `config.yml`
- System requirements in documentation
"""
        
        return readme


class ModelImporter:
    """Import/update models in EmberEye installations."""
    
    def __init__(self, embereye_install_dir: str):
        """
        Initialize with EmberEye installation directory.
        
        Args:
            embereye_install_dir: Path to EmberEye installation
                e.g., "/Applications/EmberEye" (macOS)
                e.g., "C:\\Program Files\\EmberEye" (Windows)
        """
        self.install_dir = Path(embereye_install_dir)
        self.models_dir = self.install_dir / "models"
        self.backup_dir = self.install_dir / "models" / "backups"
    
    def import_model_package(self, package_zip_path: str, device_type: str = "auto") -> Tuple[bool, str]:
        """
        Import a model package into EmberEye installation.
        
        Args:
            package_zip_path: Path to deployment package zip file
            device_type: Device type to import ("cpu", "gpu", "mps", "auto")
        
        Returns:
            (success: bool, message: str)
        """
        try:
            package_zip = Path(package_zip_path)
            if not package_zip.exists():
                return False, f"Package not found: {package_zip}"
            
            # Create models directory if needed
            self.models_dir.mkdir(parents=True, exist_ok=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract package
            extract_dir = self.models_dir / "temp_extract"
            extract_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(package_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            logger.info(f"📦 Extracted package to {extract_dir}")
            
            # Load manifest
            manifest_path = None
            for f in extract_dir.rglob("deployment_manifest.json"):
                manifest_path = f
                break
            
            if not manifest_path:
                return False, "deployment_manifest.json not found in package"
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Auto-detect device if needed
            if device_type == "auto":
                device_type = self._auto_detect_device()
                logger.info(f"Auto-detected device: {device_type}")
            
            # Get model filename for device type
            model_map = {
                'cpu': 'EmberEye.pt',
                'gpu': 'EmberEye_gpu.pt',
                'mps': 'EmberEye_mps.pt'
            }
            
            model_filename = model_map.get(device_type)
            if not model_filename:
                return False, f"Unknown device type: {device_type}"
            
            # Find model file in extracted package
            model_src = None
            for f in extract_dir.rglob(model_filename):
                model_src = f
                break
            
            if not model_src:
                return False, f"Model file {model_filename} not found in package"
            
            # Backup current model
            current_model = self.models_dir / "EmberEye.pt"
            if current_model.exists():
                backup_name = f"EmberEye_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pt"
                backup_path = self.backup_dir / backup_name
                shutil.copy(current_model, backup_path)
                logger.info(f"✓ Backed up current model to {backup_path}")
            
            # Install new model
            dest_model = self.models_dir / "EmberEye.pt"
            shutil.copy(model_src, dest_model)
            logger.info(f"✓ Installed new model: {dest_model}")
            
            # Copy config if exists
            config_map = {
                'cpu': 'EmberEye_config.json',
                'gpu': 'EmberEye_gpu_config.json',
                'mps': 'EmberEye_mps_config.json'
            }
            
            config_filename = config_map.get(device_type)
            config_src = None
            for f in extract_dir.rglob(config_filename):
                config_src = f
                break
            
            if config_src:
                config_dest = self.models_dir / "EmberEye_config.json"
                shutil.copy(config_src, config_dest)
                logger.info(f"✓ Installed model configuration")
            
            # Clean up extracted files
            shutil.rmtree(extract_dir)
            
            logger.info(f"✅ Model import complete")
            return True, f"Successfully imported {model_filename} ({device_type} optimized)"
        
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return False, f"Import error: {e}"
    
    def _auto_detect_device(self) -> str:
        """Auto-detect available device on client machine."""
        try:
            # Try NVIDIA GPU
            import subprocess
            try:
                subprocess.run(["nvidia-smi"], capture_output=True, check=True)
                return "gpu"
            except:
                pass
            
            # Try Apple MPS
            import platform
            if platform.system() == "Darwin":
                mac_version = tuple(map(int, platform.release().split(".")))
                if mac_version >= (21, 3):  # macOS 12.3+
                    return "mps"
            
            # Default to CPU
            return "cpu"
        except:
            return "cpu"
    
    def verify_installation(self) -> Tuple[bool, Dict]:
        """Verify model installation is correct."""
        try:
            status = {
                'install_dir': str(self.install_dir),
                'models_dir': str(self.models_dir),
                'model_exists': (self.models_dir / "EmberEye.pt").exists(),
                'config_exists': (self.models_dir / "EmberEye_config.json").exists(),
                'backups': list(self.backup_dir.glob("EmberEye_backup_*.pt")) if self.backup_dir.exists() else []
            }
            
            is_valid = status['model_exists'] and status['config_exists']
            return is_valid, status
        except Exception as e:
            return False, {'error': str(e)}


# Example usage
if __name__ == "__main__":
    print("Model Export & Deployment System")
    print("=" * 50)
    
    # Example 1: Export model
    print("\n1️⃣  EXPORTING MODEL")
    exporter = ModelExporter("./models/yolo_versions")
    success, msg = exporter.export_trained_model("v1")
    print(f"Export: {msg}")
    
    # Example 2: Create deployment package
    print("\n2️⃣  CREATING DEPLOYMENT PACKAGE")
    deployer = ModelDeployer("./models/yolo_versions/exports")
    success, package_path = deployer.create_deployment_package("v1", target_os="auto", device_type="all")
    if success:
        print(f"Package: {package_path}")
    
    # Example 3: Import on client machine
    print("\n3️⃣  IMPORTING ON CLIENT MACHINE")
    importer = ModelImporter("/path/to/embereye/installation")
    success, msg = importer.import_model_package(package_path, device_type="auto")
    print(f"Import: {msg}")
    
    # Example 4: Verify installation
    print("\n4️⃣  VERIFYING INSTALLATION")
    is_valid, status = importer.verify_installation()
    print(f"Valid: {is_valid}")
    print(f"Status: {status}")
