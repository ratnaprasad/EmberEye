"""
Hybrid Fire/Hazard Detection System
Combines fast heuristic filtering with accurate YOLO model detection
"""
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Dict, List
from pathlib import Path
import sys
import os

from .detection_queue import DetectionQueue, FrameMetadata, DetectionResult, get_detection_queue


class HybridDetector:
    """
    Two-stage detection pipeline:
    1. Heuristic (fast) - filters 70-80% of frames
    2. YOLO (async) - validates suspicious frames with ML model
    
    Confidence levels:
    - >= 0.80: CONFIRMED (red alert)
    - 0.60-0.80: POSSIBLE (orange warning)
    - < 0.60: LOW (ignore)
    """
    
    def __init__(self, model_path: Optional[str] = None, stream_id: str = "default"):
        self.stream_id = stream_id
        self.model = None
        self.model_loaded = False
        self.yolo_model_path = model_path
        self.last_load_error = None
        self.inference_device = "cpu"
        self.central_class_names: List[str] = []
        conf_env = os.environ.get("EMBEREYE_YOLO_CONF", "0.05")
        try:
            self.yolo_conf_threshold = float(conf_env)
        except Exception:
            self.yolo_conf_threshold = 0.05
        if self.yolo_conf_threshold < 0.001:
            self.yolo_conf_threshold = 0.001
        if self.yolo_conf_threshold > 0.9:
            self.yolo_conf_threshold = 0.9

        print(f"[HybridDetector-{self.stream_id}] Init with model_path={model_path!r}")

        try:
            from embereye.core.class_config import get_leaf_classes
            self.central_class_names = get_leaf_classes()
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Could not load central class mapping: {e}")
        
        # Heuristic parameters
        self.heuristic_threshold = 0.20  # Skip YOLO if heuristic < 0.20
        
        # Confidence level thresholds
        self.confirmed_threshold = 0.80    # >= 0.80: CONFIRMED
        self.possible_threshold = 0.60     # 0.60-0.80: POSSIBLE
        # < 0.60: LOW (ignored)
        
        # Detection queue (shared across all streams)
        self.detection_queue = get_detection_queue()
        
        # Frame counter for this stream
        self._frame_counter = 0
        self._results_received = 0
        
        # Class priority (higher = more important)
        self.class_priority = {
            'PERSON_IN_DISTRESS': 0.95,
            'FIRE': 0.95,
            'SMOKE_WITH_FIRE': 0.90,
            'EXPLOSIVE_DEVICE': 0.98,
            'EXPLOSION': 0.95,
            'ELECTRICAL_ARC': 0.85,
            'PERSON_WITHOUT_SAFETY_WEAR': 0.60,
            'DAMAGED_EQUIPMENT': 0.65,
            'HARMFUL_GASES': 0.75,
            'HAZARD_UNSPECIFIED': 0.40,
        }
        
        # Try to load YOLO model
        env_model_path = os.environ.get("YOLO_MODEL_PATH")
        if env_model_path:
            self._load_yolo_model(env_model_path)
        elif model_path:
            self._load_yolo_model(model_path)
        else:
            self._auto_load_model()
    
    def _auto_load_model(self) -> None:
        """Automatically find and load latest model from ModelVersionManager or ./models/"""
        print(f"[HybridDetector-{self.stream_id}] Auto-load model starting...")
        # First, try to use ModelVersionManager (preferred location for imported models)
        try:
            from embereye.core.model_versioning import ModelVersionManager
            manager = ModelVersionManager()
            current_best = manager.get_current_best()
            if current_best and current_best.exists():
                print(f"[HybridDetector-{self.stream_id}] ModelVersionManager best: {current_best}")
                self._load_yolo_model(str(current_best))
                return
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Could not use ModelVersionManager: {e}")
        
        # Fallback: Check for loose .pt files in ./models/
        models_dir = Path("./models")
        if models_dir.exists():
            model_files = sorted(
                [f for f in models_dir.glob("*.pt") if f.is_file() and not f.name.startswith(".")],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if model_files:
                print(f"[HybridDetector-{self.stream_id}] Using loose model file: {model_files[0]}")
                self._load_yolo_model(str(model_files[0]))
                return
        
        print(f"[HybridDetector-{self.stream_id}] No model found in ModelVersionManager or ./models/")
    
    def _ensure_torch_dlls(self) -> None:
        """Best-effort add torch DLL directories to PATH (Windows)."""
        try:
            repo_root = Path(__file__).parent.parent.parent.resolve()
            candidates = []
            if getattr(sys, "frozen", False):
                meipass = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
                candidates.append(meipass)
            env_venv = os.environ.get("EMBEREYE_VENV_PATH")
            if env_venv:
                candidates.append(Path(env_venv))
            candidates.append(repo_root / ".venv")
            candidates.append(Path(sys.executable).parent.parent)

            for base_path in candidates:
                base_candidates = [
                    base_path,
                    base_path / "_internal",
                    base_path / "Lib" / "site-packages",
                ]
                torch_lib_candidates = [
                    base_path / "Lib" / "site-packages" / "torch" / "lib",
                    base_path / "torch" / "lib",
                    base_path / "_internal" / "torch" / "lib",
                ]
                torch_lib_path = next((p for p in torch_lib_candidates if p.exists()), None)
                if torch_lib_path is None:
                    continue

                dll_dirs = [p for p in (base_candidates + [torch_lib_path]) if p.exists()]
                path_value = os.environ.get("PATH", "")
                for dll_dir in dll_dirs:
                    dll_dir_str = str(dll_dir)
                    if dll_dir_str not in path_value:
                        path_value = dll_dir_str + os.pathsep + path_value
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(dll_dir_str)
                        except Exception:
                            pass

                os.environ["PATH"] = path_value
                break
        except Exception:
            pass

    def _load_yolo_model(self, model_path: str) -> None:
        """Load YOLO model (must be called in worker thread to avoid DLL issues)"""
        self._ensure_torch_dlls()
        try:
            force_cpu = os.environ.get("EMBEREYE_FORCE_CPU", "").strip().lower() in ("1", "true", "yes")

            # In frozen builds treat CUDA_VISIBLE_DEVICES="" / "-1" as force-cpu
            if getattr(sys, "frozen", False):
                cuda_vis = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
                if cuda_vis in ("-1", ""):
                    force_cpu = True

            # Normalize path to avoid escape sequence issues
            normalized_path = model_path.replace('\\', '/')
            exists = os.path.exists(normalized_path)

            def _attempt_load(cpu_only: bool):
                import torch
                if cpu_only:
                    os.environ["CUDA_VISIBLE_DEVICES"] = ""
                    os.environ["USE_CUDA"] = "0"
                    # Monkey-patch torch.cuda.is_available so neither our
                    # code nor ultralytics ever attempts a CUDA DLL load.
                    torch.cuda.is_available = lambda: False

                from ultralytics import YOLO
                device = "cpu" if cpu_only or not torch.cuda.is_available() else "0"
                print(f"[HybridDetector-{self.stream_id}] Loading YOLO from: {normalized_path} (exists={exists}, device={device})")
                # Force map_location='cpu' so torch.load never touches CUDA
                loaded_model = YOLO(normalized_path, task="detect")
                if device == "cpu":
                    loaded_model.to("cpu")
                return loaded_model, device

            try:
                loaded_model, device = _attempt_load(force_cpu)
            except OSError as first_err:
                err_text = str(first_err).lower()
                dll_issue = ("dll" in err_text) or ("initialization routine failed" in err_text)
                if (not force_cpu) and dll_issue:
                    print(f"[HybridDetector-{self.stream_id}] [WARN] GPU load failed ({first_err!r}); retrying in CPU-only mode")
                    os.environ["EMBEREYE_FORCE_CPU"] = "1"
                    # Don't call _ensure_torch_dlls again – DLL paths are already set
                    loaded_model, device = _attempt_load(True)
                else:
                    raise

            self.model = loaded_model
            self.inference_device = device
            self.model_loaded = True
            self.last_load_error = None
            self.yolo_model_path = normalized_path
            print(f"[HybridDetector-{self.stream_id}] [OK] Model loaded. Classes: {len(self.model.names)}")
        except OSError as e:
            self.last_load_error = repr(e)
            if 'DLL' in str(e) or 'initialization routine' in str(e):
                print(f"[HybridDetector-{self.stream_id}] [WARN] DLL init error, fallback to heuristic-only: {e!r}")
            else:
                print(f"[HybridDetector-{self.stream_id}] [ERROR] Failed to load model from {model_path}: {e!r}")
            self.model_loaded = False
            self.model = None
        except Exception as e:
            self.last_load_error = repr(e)
            print(f"[HybridDetector-{self.stream_id}] [ERROR] Failed to load model from {model_path}: {e!r}")
            self.model_loaded = False
            self.model = None
    
    def heuristic_detect(self, frame: np.ndarray) -> float:
        """
        Fast heuristic detection (fire/smoke colors).
        Returns confidence score 0-1.
        
        < 0.20: Not suspicious, skip YOLO
        >= 0.20: Suspicious, queue for YOLO validation
        """
        try:
            # Convert to HSV for color analysis
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, w = frame.shape[:2]
            
            # Fire detection: warm colors (orange/red/yellow)
            # Hue: 0-40 (red wraps around), Saturation: 100-255, Value: 100-255
            lower_fire = np.array([0, 100, 100])
            upper_fire = np.array([40, 255, 255])
            mask_fire = cv2.inRange(hsv, lower_fire, upper_fire)
            fire_pixels = cv2.countNonZero(mask_fire)
            fire_ratio = fire_pixels / (h * w)
            
            # Smoke detection: low saturation, high brightness (gray/white)
            # Hue: any, Saturation: 0-60, Value: 180-255
            lower_smoke = np.array([0, 0, 180])
            upper_smoke = np.array([180, 60, 255])
            mask_smoke = cv2.inRange(hsv, lower_smoke, upper_smoke)
            smoke_pixels = cv2.countNonZero(mask_smoke)
            smoke_ratio = smoke_pixels / (h * w)
            
            # Combine with weights
            # Fire is more critical, weight 3x; smoke 1.5x
            score = min(1.0, fire_ratio * 3 + smoke_ratio * 1.5)
            
            return score
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] Heuristic error: {e}")
            return 0.0
    
    def detect_frame(self, frame: np.ndarray) -> Tuple[float, Optional[DetectionResult]]:
        """
        Main detection entry point for video frames.
        
        Returns:
            (heuristic_score, result_or_None)
            - heuristic_score: 0-1, always returned
            - result: DetectionResult if YOLO processing complete, else None
        """
        self._frame_counter += 1
        frame_id = f"{self.stream_id}-{self._frame_counter}"
        
        # Stage 1: Heuristic (fast)
        heuristic_score = self.heuristic_detect(frame)
        
        # Stage 2: Queue suspicious frames for YOLO
        if heuristic_score >= self.heuristic_threshold and self.model_loaded:
            # Create frame metadata for async YOLO processing
            metadata = FrameMetadata(
                frame_id=frame_id,
                stream_id=self.stream_id,
                heuristic_score=heuristic_score,
                frame_data=frame.copy()  # Store frame data
            )
            self.detection_queue.add_frame(metadata)
        
        # Stage 3: Check if previous results are available
        # Look for any completed results waiting for this stream
        result = self._check_pending_results()
        
        return heuristic_score, result
    
    def _check_pending_results(self) -> Optional[DetectionResult]:
        """Check if any detection results are ready for this stream"""
        # In real implementation, this would check for cached results
        # For now, we'll leave this for the video_worker to handle
        return None
    
    def map_to_confidence_level(self, yolo_confidence: float) -> str:
        """
        Map YOLO confidence to user-friendly level.
        
        >= confirmed_threshold: CONFIRMED (red)
        possible_threshold-confirmed_threshold: POSSIBLE (orange)
        < possible_threshold: LOW (gray)
        """
        if yolo_confidence >= self.confirmed_threshold:
            return "CONFIRMED"
        elif yolo_confidence >= self.possible_threshold:
            return "POSSIBLE"
        else:
            return "LOW"
    
    def process_queued_frame(self, metadata: FrameMetadata) -> DetectionResult:
        """
        Process a queued frame with YOLO (runs in worker thread).
        
        Called by detection worker thread.
        """
        start_time = time.time()
        
        if not self.model_loaded or self.model is None:
            # Model not available, return LOW confidence
            return DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status="LOW",
                confidence=0.0,
                primary_class="NO_MODEL",
                yolo_latency_ms=0.0,
                timestamp_ms=metadata.timestamp_ms
            )
        
        try:
            # Run YOLO inference
            frame = metadata.frame_data
            if frame is None:
                return DetectionResult(
                    frame_id=metadata.frame_id,
                    stream_id=metadata.stream_id,
                    status="LOW",
                    confidence=0.0,
                    yolo_latency_ms=time.time() - start_time
                )
            
            # Inference
            results = self.model(
                frame,
                verbose=False,
                conf=self.yolo_conf_threshold,
                device=self.inference_device,
            )
            
            detections = []
            max_confidence = 0.0
            primary_class = ""
            
            # Extract detections
            if results and len(results) > 0:
                for result in results:
                    if result.boxes is not None:
                        for box in result.boxes:
                            class_id = int(box.cls[0])
                            confidence = float(box.conf[0])
                            if 0 <= class_id < len(self.central_class_names):
                                class_name = self.central_class_names[class_id]
                            else:
                                class_name = self.model.names.get(class_id, f"class_{class_id}")
                            
                            detections.append({
                                'class': class_name,
                                'confidence': confidence,
                                'bbox': box.xyxy[0].cpu().numpy().tolist() if hasattr(box.xyxy, 'cpu') else box.xyxy[0].tolist()
                            })
                            
                            # Track highest confidence
                            if confidence > max_confidence:
                                max_confidence = confidence
                                primary_class = class_name
            
            # Determine confidence level
            status = self.map_to_confidence_level(max_confidence)
            latency_ms = (time.time() - start_time) * 1000
            
            result = DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status=status,
                confidence=max_confidence,
                detections=detections,
                primary_class=primary_class,
                yolo_latency_ms=latency_ms,
                timestamp_ms=metadata.timestamp_ms
            )
            
            return result
            
        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] YOLO inference error: {e}")
            return DetectionResult(
                frame_id=metadata.frame_id,
                stream_id=metadata.stream_id,
                status="LOW",
                confidence=0.0,
                yolo_latency_ms=time.time() - start_time
            )
