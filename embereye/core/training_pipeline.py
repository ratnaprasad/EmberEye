"""
Production-grade YOLO training pipeline for cross-platform deployment (GPU/CPU).
Supports: Windows, macOS, Linux with automatic device detection.
"""

import os
import json
import yaml
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
import numpy as np
import cv2
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class DeviceType(Enum):
    """Supported device types for training."""
    GPU = "gpu"
    CPU = "cpu"
    MPS = "mps"  # Apple Metal Performance Shaders


class TrainingStatus(Enum):
    """Training lifecycle states."""
    IDLE = "idle"
    PREPARING = "preparing"
    VALIDATING = "validating"
    TRAINING = "training"
    VALIDATING_FINAL = "validating_final"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class TrainingConfig:
    """Configuration for YOLO training."""
    project_name: str = "embereye_custom"
    model_size: str = "n"  # nano, small, medium, large, xlarge
    epochs: int = 100
    batch_size: int = 16
    imgsz: int = 640
    patience: int = 20  # Early stopping
    device: str = "auto"  # auto, 0, 1, cpu, mps
    lr0: float = 0.01  # Initial learning rate
    momentum: float = 0.937
    weight_decay: float = 0.0005
    augment: bool = True
    flipud: float = 0.5  # Probability
    fliplr: float = 0.5
    mosaic: float = 1.0
    mixup: float = 0.1
    save_best_only: bool = True
    save_period: int = 10
    val_split: float = 0.15
    test_split: float = 0.0  # Set to > 0 to create test set
    seed: int = 42
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TrainingProgress:
    """Real-time training progress."""
    status: TrainingStatus = TrainingStatus.IDLE
    current_epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    val_loss: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    map50: float = 0.0
    map: float = 0.0
    eta_seconds: int = 0
    gpu_memory_mb: float = 0.0
    message: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'status': self.status.value,
            'current_epoch': self.current_epoch,
            'total_epochs': self.total_epochs,
            'loss': round(self.loss, 4),
            'val_loss': round(self.val_loss, 4),
            'precision': round(self.precision, 4),
            'recall': round(self.recall, 4),
            'map50': round(self.map50, 4),
            'map': round(self.map, 4),
            'eta_seconds': self.eta_seconds,
            'gpu_memory_mb': round(self.gpu_memory_mb, 2),
            'message': self.message
        }


class DeviceManager:
    """Detect and manage training devices (GPU/CPU/MPS)."""
    
    @staticmethod
    def get_available_devices() -> Dict[str, any]:
        """Detect all available training devices."""
        devices = {
            'gpu': False,
            'gpu_name': None,
            'gpu_count': 0,
            'cpu': True,
            'mps': False,  # Apple Metal
            'recommended': 'cpu'
        }
        
        try:
            import torch
            
            # Check CUDA (NVIDIA GPUs)
            if torch.cuda.is_available():
                devices['gpu'] = True
                devices['gpu_count'] = torch.cuda.device_count()
                devices['gpu_name'] = torch.cuda.get_device_name(0)
                devices['recommended'] = '0'  # Use first GPU
                logger.info(f"✓ CUDA GPU detected: {devices['gpu_name']} (count: {devices['gpu_count']})")
            
            # Check MPS (Apple Silicon)
            elif torch.backends.mps.is_available():
                devices['mps'] = True
                devices['recommended'] = 'mps'
                logger.info("✓ Apple Metal (MPS) detected")
            
            else:
                logger.info("✓ Using CPU (no GPU detected)")
        
        except Exception as e:
            logger.warning(f"Device detection error: {e}")
        
        return devices
    
    @staticmethod
    def resolve_device(device: str = "auto") -> str:
        """Resolve device string to actual device."""
        if device == "auto":
            devices = DeviceManager.get_available_devices()
            device = devices['recommended']
        return str(device)


class DatasetManager:
    """Manage dataset preparation, splitting, and validation."""
    
    def __init__(self, base_dir: str = "./training_data"):
        self.base_dir = Path(base_dir)
        self.annotations_dir = self.base_dir / "annotations"
        self.dataset_dir = self.base_dir / "dataset"
        self.splits = {
            'train': self.dataset_dir / 'images' / 'train',
            'val': self.dataset_dir / 'images' / 'val',
            'test': self.dataset_dir / 'images' / 'test'
        }
        self.labels_splits = {
            'train': self.dataset_dir / 'labels' / 'train',
            'val': self.dataset_dir / 'labels' / 'val',
            'test': self.dataset_dir / 'labels' / 'test'
        }
    
    def prepare_dataset(self, config: TrainingConfig) -> Tuple[bool, str]:
        """
        Prepare dataset from annotation files.
        Organizes into train/val/test with YOLO structure.
        """
        try:
            logger.info("📊 Preparing dataset...")
            
            # Clear stale cache files before dataset preparation
            self._clear_cache_files()
            
            # Create directory structure
            for split in self.splits.values():
                split.mkdir(parents=True, exist_ok=True)
            for split in self.labels_splits.values():
                split.mkdir(parents=True, exist_ok=True)
            
            # Collect all annotation files
            annotation_files = self._collect_annotations()
            if not annotation_files:
                return False, "No annotations found!"
            
            logger.info(f"Found {len(annotation_files)} annotation files")
            
            # Validate annotations
            valid_files = self._validate_annotations(annotation_files)
            if not valid_files:
                return False, "No valid annotations after validation"
            
            logger.info(f"✓ {len(valid_files)} valid annotations")
            
            # Split dataset
            self._split_dataset(valid_files, config)
            
            # Generate dataset.yaml
            self._generate_yaml_config(config)
            
            logger.info("✓ Dataset preparation complete")
            return True, "Dataset ready for training"
        
        except Exception as e:
            error_msg = f"Dataset preparation error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def _clear_cache_files(self):
        """Delete stale YOLO cache files to ensure fresh dataset validation."""
        cache_dir = self.dataset_dir / 'labels'
        if cache_dir.exists():
            for cache_file in cache_dir.glob('*.cache'):
                try:
                    cache_file.unlink()
                    logger.debug(f"Deleted stale cache: {cache_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete cache {cache_file.name}: {e}")
    
    def _collect_annotations(self) -> List[Path]:
        """Collect all annotation files recursively."""
        annotations = []
        if self.annotations_dir.exists():
            for root, dirs, files in os.walk(self.annotations_dir):
                for file in files:
                    if file.endswith('.txt') and file != 'labels.txt':
                        annotations.append(Path(root) / file)
        return annotations
    
    def _validate_annotations(self, files: List[Path]) -> List[Path]:
        """Validate YOLO format annotations."""
        valid = []
        for file in files:
            try:
                with open(file, 'r') as f:
                    lines = f.readlines()
                    if not lines:
                        continue
                    for line in lines:
                        parts = line.strip().split()
                        if len(parts) != 5:
                            continue
                        # Validate: class_id [0,1] x [0,1] y [0,1] w [0,1] h [0,1]
                        class_id = int(parts[0])
                        coords = [float(p) for p in parts[1:]]
                        if 0 <= class_id and all(0 <= c <= 1 for c in coords):
                            valid.append(file)
                            break
            except:
                continue
        return valid
    
    def _split_dataset(self, files: List[Path], config: TrainingConfig):
        """Split dataset into train/val/test."""
        np.random.seed(config.seed)
        np.random.shuffle(files)
        
        total = len(files)
        val_split = int(total * config.val_split)
        test_split = int(total * config.test_split)
        
        val_files = files[:val_split]
        test_files = files[val_split:val_split + test_split]
        train_files = files[val_split + test_split:]
        
        self._copy_split(train_files, 'train')
        self._copy_split(val_files, 'val')
        if test_files:
            self._copy_split(test_files, 'test')
        
        logger.info(f"Train: {len(train_files)}, Val: {len(val_files)}, Test: {len(test_files)}")
    
    def _copy_split(self, files: List[Path], split: str):
        """Copy files to split directory."""
        copied = 0
        skipped = 0
        for ann_file in files:
            # Find corresponding image (same directory as annotation)
            img_file = ann_file.with_suffix('.jpg')
            if not img_file.exists():
                img_file = ann_file.with_suffix('.png')
            if not img_file.exists():
                img_file = ann_file.with_suffix('.jpeg')
            
            if img_file.exists():
                shutil.copy(img_file, self.splits[split] / img_file.name)
                shutil.copy(ann_file, self.labels_splits[split] / ann_file.name)
                copied += 1
            else:
                logger.warning(f"No image found for annotation: {ann_file.name}")
                skipped += 1
        
        logger.info(f"{split}: copied {copied} pairs, skipped {skipped} (no matching image)")
    
    def _generate_yaml_config(self, config: TrainingConfig):
        """Generate YOLO dataset.yaml configuration."""
        # Auto-detect classes from master_class_config - MUST match annotation_tool order
        try:
            from master_class_config import load_master_classes
            classes_dict = load_master_classes()
            # Collect leaf classes in exact same order as annotation_tool does
            leaf_classes = []
            for category in classes_dict.get("IncidentEnvironment", []) or []:
                for leaf in classes_dict.get(category, []) or []:
                    leaf_classes.append(leaf)
            
            nc = len(leaf_classes) if leaf_classes else 1
            names = leaf_classes if leaf_classes else ['fire']
            logger.info(f"Detected {nc} classes from master_class_config: {names}")
        except Exception as e:
            logger.warning(f"Could not load classes from master_class_config: {e}, using default")
            nc = 1
            names = ['fire']
        
        dataset_config = {
            'path': str(self.dataset_dir.absolute()),
            'train': 'images/train',
            'val': 'images/val',
            'test': 'images/test' if (self.dataset_dir / 'images' / 'test').exists() else None,
            'nc': nc,
            'names': names
        }
        
        # Remove test if not used
        if dataset_config['test'] is None:
            del dataset_config['test']
        
        yaml_path = self.dataset_dir / 'dataset.yaml'
        with open(yaml_path, 'w') as f:
            yaml.dump(dataset_config, f, default_flow_style=False)
        
        logger.info(f"✓ Dataset config saved: {yaml_path}")
    
    def get_dataset_stats(self) -> Dict:
        """Get dataset statistics."""
        stats = {}
        for split in ['train', 'val', 'test']:
            img_count = len(list(self.splits[split].glob('*.*')))
            stats[split] = img_count
        return stats


class YOLOTrainingPipeline:
    """Production-grade YOLO training pipeline."""
    
    def __init__(self, base_dir: str = "./training_data", config: Optional[TrainingConfig] = None):
        self.base_dir = Path(base_dir)
        self.config = config or TrainingConfig()
        self.progress = TrainingProgress()
        self.dataset_manager = DatasetManager(base_dir)
        self.device = DeviceManager.resolve_device(self.config.device)
        self.model = None
        self.training_active = False
        self.epoch_callback = None  # Callback for epoch progress: callback(current_epoch, total_epochs)
        self.progress_callback = None  # Callback with TrainingProgress object for rich updates
        self.train_seconds: int = 0
        self.final_metrics: Dict[str, float] = {}
    
    def set_epoch_callback(self, callback):
        """Set callback function for epoch progress updates.
        
        Args:
            callback: Function with signature callback(current_epoch: int, total_epochs: int)
        """
        self.epoch_callback = callback

    def set_progress_callback(self, callback):
        """Set callback for rich progress updates.
        
        Args:
            callback: Function with signature callback(progress: TrainingProgress)
        """
        self.progress_callback = callback
    
    def run_full_pipeline(self) -> Tuple[bool, str]:
        """Execute complete training pipeline."""
        try:
            logger.info("=" * 60)
            logger.info("🚀 EMBEREYE YOLO TRAINING PIPELINE")
            logger.info("=" * 60)
            
            # Step 1: Device detection
            self.progress.status = TrainingStatus.PREPARING
            devices = DeviceManager.get_available_devices()
            logger.info(f"Device: {self.device}")
            
            # Step 2: Dataset preparation
            success, msg = self.dataset_manager.prepare_dataset(self.config)
            if not success:
                self.progress.status = TrainingStatus.ERROR
                self.progress.error = msg
                return False, msg
            
            stats = self.dataset_manager.get_dataset_stats()
            logger.info(f"Dataset stats: {stats}")
            # Emit dataset ready status
            try:
                self.progress.status = TrainingStatus.VALIDATING
                self.progress.message = f"Dataset ready: train {stats.get('train',0)}, val {stats.get('val',0)}, test {stats.get('test',0)}"
                if self.progress_callback:
                    self.progress_callback(self.progress)
            except Exception:
                pass
            
            # Step 3: Start training
            success, msg = self.start_training()
            
            if success:
                self.progress.status = TrainingStatus.COMPLETE
                logger.info("✓ Training completed successfully!")
            else:
                self.progress.status = TrainingStatus.ERROR
                logger.error(f"Training failed: {msg}")
            
            logger.info("=" * 60)
            return success, msg
        
        except Exception as e:
            error_msg = f"Pipeline error: {e}"
            logger.error(error_msg)
            self.progress.status = TrainingStatus.ERROR
            self.progress.error = error_msg
            return False, error_msg
    
    def start_training(self) -> Tuple[bool, str]:
        """Start YOLO model training."""
        try:
            from ultralytics import YOLO
            from ultralytics.utils import callbacks
            import time
            
            self.progress.status = TrainingStatus.TRAINING
            self.progress.total_epochs = self.config.epochs
            
            logger.info(f"Loading model: yolov8{self.config.model_size}.pt")
            self.model = YOLO(f'yolov8{self.config.model_size}.pt')
            
            # Add callback for epoch progress tracking
            if self.epoch_callback:
                def on_train_epoch_end(trainer):
                    """Called at end of each training epoch."""
                    current_epoch = trainer.epoch + 1  # YOLO uses 0-based indexing
                    total_epochs = trainer.epochs
                    self.progress.current_epoch = current_epoch
                    self.progress.total_epochs = total_epochs

                    # Try to extract metrics/loss from trainer
                    loss = 0.0
                    val_loss = 0.0
                    precision = 0.0
                    recall = 0.0
                    map50 = 0.0
                    map_combined = 0.0
                    eta_seconds = 0
                    try:
                        li = getattr(trainer, 'loss_items', None)
                        if li is not None:
                            try:
                                loss = float(li.sum()) if hasattr(li, 'sum') else float(sum([float(x) for x in li]))
                            except Exception:
                                pass
                        # Validator metrics (Ultralytics often exposes map50/map)
                        validator = getattr(trainer, 'validator', None)
                        if validator is not None and hasattr(validator, 'metrics'):
                            mm = validator.metrics
                            map50 = float(getattr(mm, 'map50', 0.0) or 0.0)
                            map_combined = float(getattr(mm, 'map', 0.0) or 0.0)
                            precision = float(getattr(mm, 'precision', 0.0) or 0.0)
                            recall = float(getattr(mm, 'recall', 0.0) or 0.0)
                        # ETA estimation if epoch_time is available
                        epoch_time = float(getattr(trainer, 'epoch_time', 0.0) or 0.0)
                        remaining = max(0, total_epochs - current_epoch)
                        eta_seconds = int(epoch_time * remaining)
                    except Exception:
                        pass

                    # Update progress object
                    self.progress.loss = float(loss or 0.0)
                    self.progress.val_loss = float(val_loss or 0.0)
                    self.progress.precision = float(precision or 0.0)
                    self.progress.recall = float(recall or 0.0)
                    self.progress.map50 = float(map50 or 0.0)
                    self.progress.map = float(map_combined or 0.0)
                    self.progress.eta_seconds = int(eta_seconds or 0)
                    self.progress.status = TrainingStatus.TRAINING
                    self.progress.message = (
                        f"Epoch {current_epoch}/{total_epochs} - "
                        f"loss {self.progress.loss:.4f}, mAP50 {self.progress.map50:.4f}"
                    )

                    # Fire simple epoch callback
                    try:
                        self.epoch_callback(current_epoch, total_epochs)
                    except Exception:
                        pass

                    # Fire rich progress callback (optional)
                    try:
                        if self.progress_callback:
                            self.progress_callback(self.progress)
                    except Exception:
                        pass
                
                # Register callback with YOLO trainer
                self.model.add_callback("on_train_epoch_end", on_train_epoch_end)
            
            dataset_yaml = self.dataset_manager.dataset_dir / 'dataset.yaml'
            
            logger.info("Starting training...")
            logger.info(f"Config: {json.dumps(self.config.to_dict(), indent=2)}")
            start_ts = time.time()
            results = self.model.train(
                data=str(dataset_yaml),
                epochs=self.config.epochs,
                batch=self.config.batch_size,
                imgsz=self.config.imgsz,
                device=self.device,
                patience=self.config.patience,
                project=str(self.base_dir / 'runs/detect'),
                name=self.config.project_name,
                save=True,  # Save checkpoints
                save_period=self.config.save_period,
                lr0=self.config.lr0,
                momentum=self.config.momentum,
                weight_decay=self.config.weight_decay,
                flipud=self.config.flipud,
                fliplr=self.config.fliplr,
                mosaic=self.config.mosaic,
                mixup=self.config.mixup,
                augment=self.config.augment,
                seed=self.config.seed,
                verbose=True
            )
            self.train_seconds = int(time.time() - start_ts)
            
            logger.info("✓ Training completed")

            # Final validation to capture metrics for metadata
            try:
                self.progress.status = TrainingStatus.VALIDATING_FINAL
                if self.progress_callback:
                    self.progress.message = "Validating final model…"
                    self.progress_callback(self.progress)
                val_results = self.model.val(data=str(dataset_yaml), device=self.device, imgsz=self.config.imgsz, verbose=False)
                # Extract metrics robustly across ultralytics versions
                metrics: Dict[str, float] = {}
                try:
                    # Newer versions expose attributes on returned object
                    mobj = getattr(val_results, 'metrics', None)
                    if mobj is not None:
                        metrics['map50'] = float(getattr(mobj, 'map50', 0.0) or 0.0)
                        metrics['map'] = float(getattr(mobj, 'map', 0.0) or 0.0)
                        metrics['precision'] = float(getattr(mobj, 'precision', 0.0) or 0.0)
                        metrics['recall'] = float(getattr(mobj, 'recall', 0.0) or 0.0)
                except Exception:
                    pass
                # Some versions return dict-like results
                try:
                    if not metrics and isinstance(val_results, dict):
                        for k in ('map50', 'map', 'precision', 'recall'):
                            metrics[k] = float(val_results.get(k, 0.0) or 0.0)
                except Exception:
                    pass
                self.final_metrics = metrics
                if self.progress_callback:
                    self.progress.message = f"Validation: mAP50 {metrics.get('map50',0.0):.4f}"
                    self.progress_callback(self.progress)
            except Exception as ve:
                logger.warning(f"Final validation failed: {ve}")
            return True, "Training successful"
        
        except ImportError:
            error = "ultralytics not installed. Install with: pip install ultralytics"
            logger.error(error)
            return False, error
        except Exception as e:
            error = f"Training error: {e}"
            logger.error(error)
            return False, error
    
    def get_best_model_path(self) -> Optional[Path]:
        """Get path to best trained model."""
        runs_dir = self.base_dir / 'runs/detect' / self.config.project_name / 'weights'
        best_model = runs_dir / 'best.pt'
        return best_model if best_model.exists() else None
    
    def export_model(self, format: str = 'onnx') -> Tuple[bool, str]:
        """Export trained model to different formats."""
        if not self.model:
            return False, "No model loaded"
        
        try:
            model_path = self.get_best_model_path()
            if not model_path:
                return False, "Best model not found"
            
            from ultralytics import YOLO
            model = YOLO(str(model_path))
            
            logger.info(f"Exporting to {format}...")
            model.export(format=format)
            
            return True, f"Model exported to {format}"
        except Exception as e:
            return False, f"Export error: {e}"


# Example usage
if __name__ == "__main__":
    # Configure training
    config = TrainingConfig(
        project_name="fire_detector_v1",
        model_size="n",  # nano for fast iteration
        epochs=100,
        batch_size=16,
        imgsz=640,
        device="auto"
    )
    
    # Run pipeline
    pipeline = YOLOTrainingPipeline(config=config)
    success, message = pipeline.run_full_pipeline()
    
    if success:
        best_model = pipeline.get_best_model_path()
        print(f"✓ Best model: {best_model}")
