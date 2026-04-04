"""
Hybrid Fire/Hazard Detection System
Combines fast heuristic filtering with accurate YOLO model detection
"""
import cv2
import numpy as np
import threading
import time
import tempfile
import traceback
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

        # Adaptive infer resolution: scale down YOLO compute when many streams are active.
        def _env_int(name: str, default: int) -> int:
            try:
                return int(float(os.environ.get(name, str(default))))
            except Exception:
                return int(default)

        self._infer_imgsz_default = max(160, _env_int("EMBEREYE_INFER_IMGSZ", 640))
        self._infer_imgsz_gt10 = max(160, _env_int("EMBEREYE_INFER_IMGSZ_GT10", 480))
        self._infer_imgsz_gt20 = max(160, _env_int("EMBEREYE_INFER_IMGSZ_GT20", 352))
        self._infer_imgsz_gt30 = max(160, _env_int("EMBEREYE_INFER_IMGSZ_GT30", 320))

        print(f"[HybridDetector-{self.stream_id}] Init with model_path={model_path!r}")

        try:
            from embereye_base.core.class_config import get_leaf_classes
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
            from embereye_base.core.model_versioning import ModelVersionManager
            manager = ModelVersionManager()
            current_best = manager.get_current_best()
            if current_best and current_best.exists():
                print(f"[HybridDetector-{self.stream_id}] ModelVersionManager best: {current_best}")
                self._load_yolo_model(str(current_best))
                return

            # Legacy recovery: load newest known weights if current_best is absent.
            candidates = []
            for version_name in manager.list_versions():
                version_dir = manager.models_dir / version_name / "weights"
                for filename in ("EmberEye.pt", "best.pt"):
                    candidate = version_dir / filename
                    if not candidate.exists():
                        continue
                    try:
                        mtime = candidate.stat().st_mtime
                    except Exception:
                        mtime = 0.0
                    candidates.append((mtime, candidate))

            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                fallback_model = candidates[0][1]
                print(f"[HybridDetector-{self.stream_id}] ModelVersionManager fallback: {fallback_model}")
                self._load_yolo_model(str(fallback_model))
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
                    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
                    os.environ["USE_CUDA"] = "0"
                    # Monkey-patch torch.cuda.is_available so neither our
                    # code nor ultralytics ever attempts a CUDA DLL load.
                    torch.cuda.is_available = lambda: False

                from ultralytics import YOLO
                device = "cpu" if cpu_only or not torch.cuda.is_available() else "0"
                print(f"[HybridDetector-{self.stream_id}] Loading YOLO from: {normalized_path} (exists={exists}, device={device})")
                loaded_model = YOLO(normalized_path, task="detect")
                if device == "cpu":
                    loaded_model.to("cpu")
                return loaded_model, device

            def _attempt_cpu_checkpoint_rewrite_and_load():
                """Fallback for CUDA-tagged checkpoints in CPU-only runtime."""
                import torch
                from ultralytics import YOLO

                os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
                os.environ["USE_CUDA"] = "0"
                torch.cuda.is_available = lambda: False

                with tempfile.NamedTemporaryFile(prefix="embereye_cpu_model_", suffix=".pt", delete=False) as tf:
                    cpu_model_path = tf.name

                try:
                    ckpt = torch.load(normalized_path, map_location="cpu")
                    torch.save(ckpt, cpu_model_path)
                    print(f"[HybridDetector-{self.stream_id}] Retrying with CPU-normalized checkpoint: {cpu_model_path}")
                    loaded_model = YOLO(cpu_model_path, task="detect")
                    loaded_model.to("cpu")
                    return loaded_model, "cpu"
                finally:
                    try:
                        os.remove(cpu_model_path)
                    except Exception:
                        pass

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
            except Exception as first_err:
                # CPU-only fallback for CUDA-tagged checkpoints saved from GPU training.
                err_text = str(first_err).lower()
                cuda_deser_issue = (
                    "deserialize object on a cuda device" in err_text
                    or "attempting to deserialize object" in err_text
                    or "cuda" in err_text and "available" in err_text
                )
                if force_cpu and cuda_deser_issue:
                    loaded_model, device = _attempt_cpu_checkpoint_rewrite_and_load()
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
            err_msg = f"[HybridDetector-{self.stream_id}] [OSError] {e!r}\nTraceback:\n{traceback.format_exc()}"
            if 'DLL' in str(e) or 'initialization routine' in str(e):
                print(f"[HybridDetector-{self.stream_id}] [WARN] DLL init error, fallback to heuristic-only:\n{err_msg}")
            else:
                print(f"[HybridDetector-{self.stream_id}] [ERROR] Failed to load model from {model_path}:\n{err_msg}")
            # Write full error to persistent log if available
            try:
                from embereye_base.utils.resource_helper import append_debug_log
                append_debug_log(
                    "field_model_status_detailed.log",
                    f"[{time.time()}] OSError during model load:\n{err_msg}\n\n",
                )
            except Exception:
                pass
            self.model_loaded = False
            self.model = None
        except Exception as e:
            self.last_load_error = repr(e)
            err_msg = f"[HybridDetector-{self.stream_id}] [Exception] {type(e).__name__}: {e!r}\nTraceback:\n{traceback.format_exc()}"
            print(f"[HybridDetector-{self.stream_id}] [ERROR] Failed to load model from {model_path}:\n{err_msg}")
            # Write full error to persistent log if available
            try:
                from embereye_base.utils.resource_helper import append_debug_log
                append_debug_log(
                    "field_model_status_detailed.log",
                    f"[{time.time()}] Exception during model load:\n{err_msg}\n\n",
                )
            except Exception:
                pass
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
        batch_results = self.process_queued_batch([metadata])
        return batch_results[0] if batch_results else self._low_result(metadata, 0.0, primary_class="NO_RESULT")

    def _resolve_infer_imgsz(self) -> int:
        """Select YOLO inference image-size from active stream count."""
        try:
            active_streams = int(self.detection_queue.get_stats().get('active_streams', 0))
        except Exception:
            active_streams = 0
        if active_streams > 30:
            return self._infer_imgsz_gt30
        if active_streams > 20:
            return self._infer_imgsz_gt20
        if active_streams > 10:
            return self._infer_imgsz_gt10
        return self._infer_imgsz_default

    def _resolve_class_name(self, class_id: int) -> str:
        model_names = getattr(self.model, 'names', None)
        class_name = None
        if isinstance(model_names, dict):
            class_name = model_names.get(class_id)
        elif isinstance(model_names, list) and 0 <= class_id < len(model_names):
            class_name = model_names[class_id]
        if class_name is None:
            if 0 <= class_id < len(self.central_class_names):
                class_name = self.central_class_names[class_id]
            else:
                class_name = f"class_{class_id}"
        return str(class_name)

    def _low_result(self, metadata: FrameMetadata, latency_ms: float, primary_class: str = "") -> DetectionResult:
        return DetectionResult(
            frame_id=metadata.frame_id,
            stream_id=metadata.stream_id,
            status="LOW",
            confidence=0.0,
            detections=[],
            primary_class=primary_class,
            yolo_latency_ms=float(latency_ms),
            timestamp_ms=metadata.timestamp_ms,
        )

    def _result_from_yolo(self, metadata: FrameMetadata, yolo_result, latency_ms: float) -> DetectionResult:
        detections = []
        max_confidence = 0.0
        primary_class = ""

        if yolo_result is not None and getattr(yolo_result, 'boxes', None) is not None:
            for box in yolo_result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = self._resolve_class_name(class_id)
                detections.append({
                    'class': class_name,
                    'confidence': confidence,
                    'bbox': box.xyxy[0].cpu().numpy().tolist() if hasattr(box.xyxy, 'cpu') else box.xyxy[0].tolist(),
                })
                if confidence > max_confidence:
                    max_confidence = confidence
                    primary_class = class_name

        return DetectionResult(
            frame_id=metadata.frame_id,
            stream_id=metadata.stream_id,
            status=self.map_to_confidence_level(max_confidence),
            confidence=max_confidence,
            detections=detections,
            primary_class=primary_class,
            yolo_latency_ms=float(latency_ms),
            timestamp_ms=metadata.timestamp_ms,
        )

    def process_queued_batch(self, metadata_batch: List[FrameMetadata]) -> List[DetectionResult]:
        """Process multiple queued frames in one YOLO call for higher multi-camera throughput."""
        if not metadata_batch:
            return []

        start_time = time.time()

        if not self.model_loaded or self.model is None:
            return [self._low_result(m, 0.0, primary_class="NO_MODEL") for m in metadata_batch]

        valid_meta = []
        valid_frames = []
        for metadata in metadata_batch:
            frame = getattr(metadata, 'frame_data', None)
            if frame is None:
                continue
            valid_meta.append(metadata)
            valid_frames.append(frame)

        if not valid_meta:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return [self._low_result(m, elapsed_ms, primary_class="NO_FRAME") for m in metadata_batch]

        try:
            infer_imgsz = self._resolve_infer_imgsz()
            yolo_results = self.model(
                valid_frames,
                verbose=False,
                conf=self.yolo_conf_threshold,
                device=self.inference_device,
                imgsz=infer_imgsz,
            )
            total_latency_ms = (time.time() - start_time) * 1000.0
            per_frame_latency_ms = total_latency_ms / max(1, len(valid_meta))

            results_by_frame_id = {}
            for metadata, yolo_result in zip(valid_meta, yolo_results):
                results_by_frame_id[metadata.frame_id] = self._result_from_yolo(metadata, yolo_result, per_frame_latency_ms)

            output = []
            for metadata in metadata_batch:
                output.append(results_by_frame_id.get(metadata.frame_id, self._low_result(metadata, per_frame_latency_ms, primary_class="NO_RESULT")))
            return output

        except Exception as e:
            print(f"[HybridDetector-{self.stream_id}] YOLO batch inference error: {e}")
            elapsed_ms = (time.time() - start_time) * 1000.0
            return [self._low_result(m, elapsed_ms, primary_class="ERROR") for m in metadata_batch]
