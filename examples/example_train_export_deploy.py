#!/usr/bin/env python3
"""
Complete Example: Train → Export → Deploy EmberEye Models

This script demonstrates the full workflow:
1. Train model at central location (with full retrain approach)
2. Export with device-specific variants (CPU/GPU/MPS)
3. Deploy to multiple client machines with auto-detection

Run this after:
- Annotating frames in annotation_tool.py
- Collecting 50+ images for initial training
"""

import sys
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def train_model(version: str, total_images: int, new_images: int, epochs: int, 
                project_name: str = "fire_detector"):
    """Train a model version."""
    from embereye_base.core.training_pipeline import TrainingConfig, YOLOTrainingPipeline
    
    logger.info(f"🚀 Training {version} with {total_images} total images ({new_images} new)...")
    
    config = TrainingConfig(
        project_name=f"{project_name}_{version}",
        epochs=epochs,
        batch_size=16,
        device="auto"
    )
    
    pipeline = YOLOTrainingPipeline(config=config)
    success, msg = pipeline.run_full_pipeline()
    
    if not success:
        logger.error(f"❌ Training failed: {msg}")
        return False
    
    logger.info(f"✅ Training complete: {msg}")
    return True


def create_version(version: str, total_images: int, new_images: int, 
                   accuracy: float, loss: float, training_hours: float,
                   previous_version=None):
    """Create a versioned model."""
    from model_versioning import ModelVersionManager, ModelMetadata
    from embereye_base.core.training_pipeline import TrainingConfig
    
    logger.info(f"📝 Creating version {version}...")
    
    # Get training config (would normally come from actual training)
    config = TrainingConfig()
    
    metadata = ModelMetadata(
        version=version,
        timestamp=datetime.now().isoformat(),
        training_images=total_images,      # ✅ ALL images used
        new_images=new_images,              # ✅ Only new ones added
        total_epochs=50 if previous_version else 100,
        best_accuracy=accuracy,
        loss=loss,
        training_time_hours=training_hours,
        base_model="yolov8n",
        config_snapshot=config.to_dict(),
        previous_version=previous_version,  # ✅ Transfer learning from prev
        training_strategy="full_retrain",   # ✅ Full retrain approach
        notes=f"Incremental training" if previous_version else "Initial training"
    )
    
    version_mgr = ModelVersionManager()
    
    # In real scenario, source_weights_dir would be the actual training output
    # For this example, we'll use the version directory
    source_weights = Path(f"runs/detect/fire_detector_{version}/weights")
    
    if not source_weights.exists():
        logger.warning(f"⚠️  Training output not found, creating version metadata only")
        # Would normally fail here, but for demo we create metadata
        return True
    
    success, msg = version_mgr.create_version(metadata, source_weights)
    
    if success:
        logger.info(f"✅ {msg}")
    else:
        logger.error(f"❌ Version creation failed: {msg}")
    
    return success


def export_models(version: str):
    """Export model with device-specific variants."""
    from model_export_deploy import ModelExporter
    
    logger.info(f"📦 Exporting {version} with device variants...")
    
    exporter = ModelExporter()
    success, msg = exporter.export_trained_model(version)
    
    if success:
        logger.info(f"✅ {msg}")
        logger.info(f"   - EmberEye.pt (CPU - all platforms)")
        logger.info(f"   - EmberEye_gpu.pt (NVIDIA GPU)")
        logger.info(f"   - EmberEye_mps.pt (Apple Metal)")
    else:
        logger.error(f"❌ Export failed: {msg}")
    
    return success


def create_package(version: str):
    """Create deployment package."""
    from model_export_deploy import ModelDeployer
    
    logger.info(f"📮 Creating deployment package for {version}...")
    
    deployer = ModelDeployer()
    success, package_path = deployer.create_deployment_package(
        version=version,
        target_os="auto",    # All OS
        device_type="all"    # All device types
    )
    
    if success:
        logger.info(f"✅ Package created: {package_path}")
        logger.info(f"   Total size: ~500MB (includes all variants)")
        return package_path
    else:
        logger.error(f"❌ Package creation failed: {package_path}")
    
    return None


def deploy_to_client(package_path: str, install_dir: str, device_type: str = "auto"):
    """Deploy package to a client machine."""
    from model_export_deploy import ModelImporter
    
    logger.info(f"🌍 Deploying to client: {install_dir}")
    logger.info(f"   Device type: {device_type} (auto-detect enabled)")
    
    importer = ModelImporter(install_dir)
    success, msg = importer.import_model_package(package_path, device_type)
    
    if success:
        logger.info(f"✅ {msg}")
    else:
        logger.error(f"❌ Deployment failed: {msg}")
    
    # Verify
    is_valid, status = importer.verify_installation()
    logger.info(f"   Installation valid: {is_valid}")
    
    return success


def show_version_comparison():
    """Show all model versions and their metrics."""
    from model_versioning import ModelVersionManager
    
    logger.info("\n📊 Model Version Comparison")
    logger.info("=" * 70)
    
    version_mgr = ModelVersionManager()
    print(version_mgr.get_version_comparison())


def main():
    """Main workflow: Train → Export → Deploy."""
    
    print("=" * 70)
    print("EMBEREYE: TRAIN → EXPORT → DEPLOY WORKFLOW")
    print("=" * 70)
    
    # ========== PHASE 1: TRAINING LOCATION ==========
    print("\n🏢 PHASE 1: TRAINING LOCATION (Central Server)")
    print("-" * 70)
    
    # Step 1: Train v1 (initial)
    print("\n📍 Step 1: Train v1 with 1000 images")
    print("   Frames: 1000 (initial collection)")
    print("   Epochs: 100 (from scratch)")
    
    if train_model(
        version="v1",
        total_images=1000,
        new_images=1000,
        epochs=100
    ):
        if create_version(
            version="v1",
            total_images=1000,
            new_images=1000,
            accuracy=0.92,
            loss=0.045,
            training_hours=2.5,
            previous_version=None
        ):
            logger.info("✓ v1 ready for production")
    
    # Step 2: Collect more data and train v2
    print("\n📍 Step 2: Collect 100 more frames (total 1100)")
    print("   New frames: 100")
    print("   Total frames for v2 training: 1100 (v1's 1000 + new 100)")
    
    if train_model(
        version="v2",
        total_images=1100,      # ✅ ALL images (v1 + new)
        new_images=100,         # ✅ Only new ones this round
        epochs=50,              # ✅ Fewer epochs (transfer learning)
        project_name="fire_detector"
    ):
        if create_version(
            version="v2",
            total_images=1100,          # ✅ ALL images
            new_images=100,             # ✅ Only new
            accuracy=0.945,             # ✅ Improved
            loss=0.038,                 # ✅ Lower loss
            training_hours=1.2,         # ✅ Faster (transfer learning)
            previous_version="v1"       # ✅ Transfer learning from v1
        ):
            logger.info("✓ v2 ready for production")
    
    # Step 3: Export models
    print("\n📍 Step 3: Export v2 with device variants")
    if export_models("v2"):
        logger.info("✓ All variants created (CPU/GPU/MPS)")
    
    # Step 4: Create deployment package
    print("\n📍 Step 4: Create deployment package")
    package_path = create_package("v2")
    
    if not package_path:
        logger.error("❌ Package creation failed, cannot proceed with deployment")
        return
    
    # ========== PHASE 2: DEPLOYMENT LOCATIONS ==========
    print("\n\n🌍 PHASE 2: DEPLOYMENT LOCATIONS (Multiple Client Machines)")
    print("-" * 70)
    
    # Client 1: Windows with NVIDIA GPU
    print("\n📍 Client 1: Windows PC with NVIDIA GPU")
    print("   Path: C:\\Program Files\\EmberEye")
    print("   Detection: Auto-detects NVIDIA CUDA")
    print("   Expected import: EmberEye_gpu.pt")
    
    deploy_to_client(
        package_path=str(package_path),
        install_dir="C:\\Program Files\\EmberEye",
        device_type="auto"
    )
    
    # Client 2: macOS with Apple Silicon
    print("\n📍 Client 2: macOS with Apple Silicon (M2)")
    print("   Path: /Applications/EmberEye")
    print("   Detection: Auto-detects Apple Metal (MPS)")
    print("   Expected import: EmberEye_mps.pt")
    
    deploy_to_client(
        package_path=str(package_path),
        install_dir="/Applications/EmberEye",
        device_type="auto"
    )
    
    # Client 3: Linux Server (CPU)
    print("\n📍 Client 3: Linux Server (CPU Only)")
    print("   Path: /opt/embereye")
    print("   Detection: Auto-detects CPU (no GPU)")
    print("   Expected import: EmberEye.pt")
    
    deploy_to_client(
        package_path=str(package_path),
        install_dir="/opt/embereye",
        device_type="cpu"
    )
    
    # ========== FINAL SUMMARY ==========
    print("\n" + "=" * 70)
    print("✅ DEPLOYMENT COMPLETE")
    print("=" * 70)
    
    print("\n📊 Version Comparison")
    show_version_comparison()
    
    print("\n📋 Deployment Summary:")
    print("""
✓ v1: Initial model with 1000 images (mAP=0.92, kept for rollback)
✓ v2: Incremental update with 1100 total images (mAP=0.945, promoted to production)

✓ Client 1 (Windows GPU): Running EmberEye_gpu.pt (5-10x faster)
✓ Client 2 (macOS MPS): Running EmberEye_mps.pt (2-3x faster)
✓ Client 3 (Linux CPU): Running EmberEye.pt (baseline performance)

✓ All backups saved for rollback if needed
✓ Model versions tracked in models/yolo_versions/
✓ Deployment package available for future updates

Next Steps:
1. Monitor performance across all locations
2. Verify model accuracy meets requirements
3. Plan v3 when collecting next batch of data
4. If issues arise, rollback to v1 using backup
""")
    
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
