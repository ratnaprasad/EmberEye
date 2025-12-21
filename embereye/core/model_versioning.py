"""
Model versioning and incremental training system for EmberEye.
Manages model lifecycle: training, versioning, incremental updates.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Track model version metadata."""
    version: str  # v1, v2, v3, etc.
    timestamp: str  # ISO format
    training_images: int  # Total images used for this version (INCLUDES all previous data)
    new_images: int  # New images added in this version only
    total_epochs: int
    best_accuracy: float  # mAP50
    loss: float
    training_time_hours: float
    base_model: str  # yolov8n, yolov8s, etc.
    config_snapshot: Dict  # TrainingConfig at time of training
    previous_version: Optional[str] = None  # Trained from weights of this version (transfer learning)
    notes: str = ""
    training_strategy: str = "full_retrain"  # full_retrain or fine_tune
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def save(self, path: Path):
        """Save metadata to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: Path):
        """Load metadata from JSON."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(**data)


class ModelVersionManager:
    """
    Manage model versions and incremental training.
    
    Structure:
    models/
    ├── v1/
    │   ├── weights/
    │   │   ├── best.pt
    │   │   └── last.pt
    │   ├── metadata.json
    │   └── training_log.txt
    ├── v2/
    │   ├── weights/
    │   │   ├── best.pt
    │   │   └── last.pt
    │   ├── metadata.json
    │   └── training_log.txt
    └── current_best.pt -> v2/weights/best.pt (symlink)
    """
    
    def __init__(self, models_dir: str = "./models/yolo_versions"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.current_best_link = self.models_dir / "current_best.pt"
        self.metadata_index = self.models_dir / "all_versions.json"
    
    def get_next_version(self) -> str:
        """Get next version number."""
        versions = self.list_versions()
        if not versions:
            return "v1"
        latest_num = max(int(v.replace('v', '')) for v in versions)
        return f"v{latest_num + 1}"
    
    def list_versions(self) -> List[str]:
        """List all model versions."""
        versions = []
        for item in self.models_dir.iterdir():
            if item.is_dir() and item.name.startswith('v') and item.name[1:].isdigit():
                versions.append(item.name)
        return sorted(versions)
    
    def create_version(self, metadata: ModelMetadata, source_weights_dir: Path) -> Tuple[bool, str]:
        """
        Create new model version from training results.
        
        CRITICAL: v2 must train on ALL images (v1's 1000 + new 100 = 1100 total)
        This ensures consistent improvement through full incremental training.
        
        Args:
            metadata: ModelMetadata with training info
                - training_images: TOTAL images used (not just new ones)
                - new_images: Only NEW images added in this round
                - previous_version: If using transfer learning from v1
                - training_strategy: "full_retrain" (recommended) or "fine_tune"
            source_weights_dir: Path to trained weights directory from YOLOv8
        """
        try:
            version_dir = self.models_dir / metadata.version
            weights_dir = version_dir / "weights"
            
            # Create version directory
            weights_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy best model with both names (best.pt for tracking, EmberEye.pt for production)
            src_best = source_weights_dir / "best.pt"
            src_last = source_weights_dir / "last.pt"
            
            if src_best.exists():
                shutil.copy(src_best, weights_dir / "best.pt")  # Internal tracking
                shutil.copy(src_best, weights_dir / "EmberEye.pt")  # Production name
            if src_last.exists():
                shutil.copy(src_last, weights_dir / "last.pt")
            
            # Save metadata
            metadata.save(version_dir / "metadata.json")
            
            # Log training strategy
            strategy_msg = f"{metadata.training_strategy}: {metadata.training_images} total images"
            if metadata.previous_version:
                strategy_msg += f" (transfer learning from {metadata.previous_version})"
            logger.info(f"✓ Created {metadata.version} with {strategy_msg}")
            
            # Update current_best symlink (now points to EmberEye.pt)
            self._update_current_best_link(metadata.version)
            
            # Update index
            self._update_index()
            
            logger.info(f"✓ Model version: {metadata.version} created successfully")
            logger.info(f"  📦 Production model: {weights_dir}/EmberEye.pt")
            logger.info(f"  📊 Total training images: {metadata.training_images}")
            logger.info(f"  ✨ New images this round: {metadata.new_images}")
            return True, f"Model {metadata.version} created (EmberEye.pt ready for export)"
        
        except Exception as e:
            error = f"Failed to create version: {e}"
            logger.error(error)
            return False, error
    
    def get_version_metadata(self, version: str) -> Optional[ModelMetadata]:
        """Get metadata for a specific version."""
        metadata_path = self.models_dir / version / "metadata.json"
        if metadata_path.exists():
            return ModelMetadata.load(metadata_path)
        return None
    
    def get_all_metadata(self) -> List[ModelMetadata]:
        """Get metadata for all versions."""
        all_metadata = []
        for version in self.list_versions():
            meta = self.get_version_metadata(version)
            if meta:
                all_metadata.append(meta)
        return sorted(all_metadata, key=lambda m: m.version)
    
    def get_current_best(self) -> Optional[Path]:
        """Get path to current best model."""
        if self.current_best_link.exists():
            return self.current_best_link.resolve()
        return None
    
    def promote_to_best(self, version: str) -> Tuple[bool, str]:
        """Promote a version to be the current best model (uses EmberEye.pt)."""
        version_best = self.models_dir / version / "weights" / "EmberEye.pt"
        if not version_best.exists():
            return False, f"Version {version} EmberEye.pt not found"
        
        try:
            self._update_current_best_link(version)
            logger.info(f"✓ Promoted {version} to current best (EmberEye.pt)")
            return True, f"{version} is now the production model (EmberEye.pt)"
        except Exception as e:
            return False, f"Promotion failed: {e}"
    
    def _update_current_best_link(self, version: str):
        """Update symlink to current best model (now points to EmberEye.pt)."""
        # Point to EmberEye.pt (production naming) instead of best.pt
        target = self.models_dir / version / "weights" / "EmberEye.pt"
        
        if self.current_best_link.exists() or self.current_best_link.is_symlink():
            self.current_best_link.unlink()
        
        # Create relative symlink for portability
        try:
            self.current_best_link.symlink_to(target)
        except (OSError, NotImplementedError):
            # Windows may not support symlinks, use copy instead
            shutil.copy(target, self.current_best_link)
    
    def _update_index(self):
        """Update index of all versions."""
        versions_info = []
        for metadata in self.get_all_metadata():
            versions_info.append({
                'version': metadata.version,
                'timestamp': metadata.timestamp,
                'training_images': metadata.training_images,
                'new_images': metadata.new_images,
                'best_accuracy': metadata.best_accuracy,
                'loss': metadata.loss
            })
        
        with open(self.metadata_index, 'w') as f:
            json.dump(versions_info, f, indent=2)
    
    def get_version_comparison(self) -> str:
        """Generate human-readable version comparison."""
        metadata_list = self.get_all_metadata()
        if not metadata_list:
            return "No versions available"
        
        report = "📊 MODEL VERSION HISTORY\n"
        report += "=" * 80 + "\n"
        report += f"{'Version':<10} {'Date':<20} {'Images':<12} {'mAP50':<10} {'Loss':<10}\n"
        report += "-" * 80 + "\n"
        
        for m in metadata_list:
            date = m.timestamp.split('T')[0]
            report += f"{m.version:<10} {date:<20} {m.training_images:<12} {m.best_accuracy:<10.4f} {m.loss:<10.4f}\n"
        
        report += "=" * 80 + "\n"
        current = self.get_current_best()
        report += f"🎯 Current Best: {current}\n"
        
        return report
    
    def delete_version(self, version: str) -> Tuple[bool, str]:
        """Delete a model version (keep metadata for history)."""
        version_dir = self.models_dir / version
        if not version_dir.exists():
            return False, f"Version {version} not found"
        
        try:
            # Don't delete if it's the current best
            current_best = self.get_current_best()
            if current_best and current_best.parent.parent.name == version:
                return False, f"Cannot delete current best model ({version})"
            
            shutil.rmtree(version_dir)
            logger.info(f"✓ Deleted model version: {version}")
            return True, f"Version {version} deleted"
        except Exception as e:
            return False, f"Deletion failed: {e}"
    
    def export_version(self, version: str, export_format: str = "onnx") -> Tuple[bool, str]:
        """Export a model version to different format."""
        model_path = self.models_dir / version / "weights" / "best.pt"
        if not model_path.exists():
            return False, f"Model {version} not found"
        
        try:
            from ultralytics import YOLO
            
            model = YOLO(str(model_path))
            export_path = model.export(format=export_format)
            logger.info(f"✓ Exported {version} to {export_format}")
            return True, f"Exported to {export_path}"
        except Exception as e:
            return False, f"Export failed: {e}"


class IncrementalTrainingManager:
    """
    Manage incremental training workflow.
    - Keep track of datasets used for each version
    - Support adding new images to existing dataset
    - Suggest when to retrain
    """
    
    def __init__(self, base_dir: str = "./training_data"):
        self.base_dir = Path(base_dir)
        self.datasets_dir = self.base_dir / "datasets"
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_history = self.datasets_dir / "history.json"
    
    def register_dataset(self, version: str, image_count: int, new_images: int):
        """Register dataset used for a training version."""
        history = self._load_history()
        history[version] = {
            'timestamp': datetime.now().isoformat(),
            'total_images': image_count,
            'new_images': new_images
        }
        self._save_history(history)
    
    def get_dataset_stats(self) -> Dict:
        """Get current dataset statistics."""
        annotations_dir = self.base_dir / "annotations"
        if not annotations_dir.exists():
            return {'total_frames': 0, 'videos': []}
        
        videos = {}
        total = 0
        
        for video_dir in annotations_dir.iterdir():
            if video_dir.is_dir():
                txt_files = list(video_dir.glob("frame_*.txt"))
                jpg_files = list(video_dir.glob("frame_*.jpg"))
                videos[video_dir.name] = {
                    'annotations': len(txt_files),
                    'images': len(jpg_files)
                }
                total += len(jpg_files)
        
        return {
            'total_frames': total,
            'videos': videos
        }
    
    def suggest_retraining(self, current_version: str, threshold: int = 100) -> Tuple[bool, str]:
        """
        Suggest retraining if enough new images added.
        
        Args:
            current_version: Current best version
            threshold: Minimum new images to trigger retraining
        """
        history = self._load_history()
        
        if current_version not in history:
            return False, "Current version not in history"
        
        current_count = history[current_version]['total_images']
        stats = self.get_dataset_stats()
        new_count = stats['total_frames']
        
        new_images = new_count - current_count
        
        if new_images >= threshold:
            return True, f"Recommended retraining: {new_images} new images (threshold: {threshold})"
        else:
            return False, f"Not enough new images ({new_images}/{threshold}) for retraining"
    
    def _load_history(self) -> Dict:
        """Load dataset history."""
        if self.dataset_history.exists():
            with open(self.dataset_history, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_history(self, history: Dict):
        """Save dataset history."""
        with open(self.dataset_history, 'w') as f:
            json.dump(history, f, indent=2)


# Example usage
if __name__ == "__main__":
    # Initialize managers
    version_mgr = ModelVersionManager()
    training_mgr = IncrementalTrainingManager()
    
    # List all versions
    print(version_mgr.get_version_comparison())
    
    # Get dataset stats
    stats = training_mgr.get_dataset_stats()
    print(f"Dataset: {stats['total_frames']} total frames")
    
    # Check if retraining recommended
    recommended, msg = training_mgr.suggest_retraining("v1", threshold=100)
    print(msg)
