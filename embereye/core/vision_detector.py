import cv2
import numpy as np
import os
import sys
from vision_logger import log_warning, log_debug, log_error

# Severity ranking helper (higher = worse)
SEVERITY_ORDER = ["NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
SEVERITY_RANK = {name: idx for idx, name in enumerate(SEVERITY_ORDER)}

# Base class-to-severity defaults (used when no context-specific rule hits)
BASE_SEVERITY = {
    "flame": "HIGH",
    "smoke": "MEDIUM",
    "smoke_heavy": "HIGH",
    "smoke_toxic": "CRITICAL",
    "spark": "MEDIUM",
    "ember": "MEDIUM",
    "hot_surface": "HIGH",
    "chemical_leak": "HIGH",
    "steam": "LOW",
    "heat_haze": "LOW",
    "bare_hand": "MEDIUM",
    "no_helmet": "MEDIUM",
    "no_gloves": "MEDIUM",
    "person": "LOW",
    "person_protected": "LOW",
    "fire_extinguisher": "LOW",
    "alarm_light": "LOW",
    "sprinkler": "LOW",
    "emergency_exit": "LOW",
    "vehicle": "LOW",
    "ship": "LOW",
    "aircraft": "LOW",
    "pressure_vessel": "HIGH",
    "equipment_overheating": "HIGH",
    "structural_deform": "MEDIUM",
    "structural_collapse": "CRITICAL",
    "damaged_vent": "MEDIUM",
    "gas_leak": "HIGH",
    "electrical_arc": "CRITICAL",
    "explosion": "CRITICAL",
    "explosive_device": "CRITICAL",
    "firearm": "CRITICAL",
    "knife": "HIGH",
    "weapon_like_object": "MEDIUM",
    "fight": "HIGH",
    "ember": "MEDIUM",
}

# Scoring knobs (0-100) inspired by the provided table
SCORE_FACTORS = {
    "flame": 40,
    "smoke_toxic": 30,
    "smoke_heavy": 25,
    "smoke": 15,
    "spark": 15,
    "ember": 12,
    "person_distress": 25,
    "confined_space": 20,
    "no_ppe": 15,
    "weapon": 40,
    "electrical_arc": 30,
    "explosion": 40,
    "gas_leak": 25,
    "pressure_vessel": 20,
}

class VisionDetector:
    def __init__(self, yolo_model_path=None):
        self.model = None
        self.model_loaded = False
        
        # Auto-detect bundled model path
        if yolo_model_path is None:
            yolo_model_path = self._get_bundled_model_path()
        
        self.yolo_model_path = yolo_model_path
        
        # Load model at initialization for offline operation
        if yolo_model_path and os.path.exists(yolo_model_path):
            self.load_model(yolo_model_path)
        else:
            log_warning(f"YOLO model not found at {yolo_model_path}. Using heuristic detection only.")

        # Cache latest classification details for optional consumers
        self.last_details = None

    def _normalize_class(self, name):
        return str(name).strip().lower().replace(" ", "_")

    def _severity_max(self, *labels):
        ranks = [SEVERITY_RANK.get(lbl, 0) for lbl in labels if lbl]
        return SEVERITY_ORDER[max(ranks)] if ranks else "NORMAL"

    def _apply_mitigation(self, severity, present_classes):
        rank = SEVERITY_RANK.get(severity, 0)
        if rank == 0:
            return severity, []
        mitigations = []
        pc = present_classes

        def reduce_once(label):
            nonlocal rank
            mitigations.append(label)
            rank = max(0, rank - 1)

        # Apply rule-based reductions
        if "person_rescuer" in pc:
            reduce_once("person_rescuer_present")
        if "fire_extinguisher" in pc:
            reduce_once("fire_extinguisher_visible")
        if "sprinkler" in pc or "sprinkler_active" in pc:
            reduce_once("sprinkler_active")
        if "alarm_light" in pc or "alarm_light_active" in pc:
            reduce_once("alarm_light_active")
        if "gloves" in pc and "bare_hand" in pc:
            reduce_once("gloves_present")
        if "helmet" in pc and "no_helmet" in pc:
            reduce_once("helmet_present")
        if "ppe" in pc or "person_protected" in pc:
            reduce_once("ppe_present")
        if "evacuation_in_progress" in pc:
            reduce_once("evacuation_in_progress")
        if "hazard_contained" in pc:
            reduce_once("hazard_contained")

        return SEVERITY_ORDER[rank], mitigations

    def _score_from_factors(self, present_classes):
        score = 0
        for cls, delta in SCORE_FACTORS.items():
            if cls in present_classes:
                score += delta
        # Boundaries and normalization
        score = max(0, min(100, score))
        # Map to textual severity for convenience
        if score >= 81:
            label = "CRITICAL"
        elif score >= 61:
            label = "HIGH"
        elif score >= 31:
            label = "MEDIUM"
        elif score >= 1:
            label = "LOW"
        else:
            label = "NORMAL"
        return score, label

    def _classify_detections(self, detections, context=None):
        """
        Apply the provided rule table to derive a threat summary.
        detections: list of {class, confidence, bbox (optional)}
        context: optional set/list of contextual flags (e.g., indoor, confined_space)
        """
        context = context or []
        present = {self._normalize_class(d.get('class')) for d in detections}
        present |= {self._normalize_class(c) for c in context}

        # Convenience helpers
        has = present.__contains__
        severity_hits = []
        reasons = []

        # CRITICAL rules
        if has("flame") and (has("indoor") or has("person_distress") or has("vehicle") or has("ship") or has("aircraft") or has("fuel_tank") or has("gas_cylinder") or has("confined_space")):
            severity_hits.append("CRITICAL")
            reasons.append("Flame with critical context")
        if has("smoke_toxic"):
            severity_hits.append("CRITICAL")
            reasons.append("Toxic smoke")
        if has("smoke_heavy") and (has("indoor") or has("confined_space")):
            severity_hits.append("CRITICAL")
            reasons.append("Heavy smoke in enclosed area")
        if has("explosion") or has("electrical_arc"):
            severity_hits.append("CRITICAL")
            reasons.append("Explosion/electrical arc")
        if has("gas_leak") and (has("flame") or has("spark")):
            severity_hits.append("CRITICAL")
            reasons.append("Gas leak with ignition source")
        if has("damaged_vent") and has("smoke_heavy"):
            severity_hits.append("CRITICAL")
            reasons.append("Damaged vent with heavy smoke")
        if has("structural_collapse"):
            severity_hits.append("CRITICAL")
            reasons.append("Structural collapse")
        if has("explosive_device") or has("firearm") or (has("knife") and has("aggressive_posture")):
            severity_hits.append("CRITICAL")
            reasons.append("Weapon detected")

        # HIGH rules
        if has("flame") and not (has("indoor") or has("confined_space")):
            severity_hits.append("HIGH")
            reasons.append("Flame (outdoor/unspecified)")
        if has("smoke_heavy") and not (has("indoor") or has("confined_space")):
            severity_hits.append("HIGH")
            reasons.append("Heavy smoke outdoor")
        if has("spark") and (has("flammable_liquid") or has("gas_leak")):
            severity_hits.append("HIGH")
            reasons.append("Spark with flammable materials")
        if has("ember") and has("combustible_material"):
            severity_hits.append("HIGH")
            reasons.append("Ember near combustibles")
        if has("hot_surface"):
            severity_hits.append("HIGH")
            reasons.append("Hot surface")
        if has("chemical_leak"):
            severity_hits.append("HIGH")
            reasons.append("Chemical leak")
        if has("smoke") and has("indoor"):
            severity_hits.append("HIGH")
            reasons.append("Smoke indoor")
        if has("pressure_vessel") and has("heat_haze"):
            severity_hits.append("HIGH")
            reasons.append("Hot pressure vessel")
        if has("equipment_overheating"):
            severity_hits.append("HIGH")
            reasons.append("Equipment overheating")
        if has("fight"):
            severity_hits.append("HIGH")
            reasons.append("Physical altercation")

        # MEDIUM rules
        if has("spark") and not (has("flammable_liquid") or has("gas_leak")):
            severity_hits.append("MEDIUM")
            reasons.append("Spark (no flammables detected)")
        if has("ember") and not has("combustible_material"):
            severity_hits.append("MEDIUM")
            reasons.append("Ember small/isolated")
        if has("smoke") and not has("indoor"):
            severity_hits.append("MEDIUM")
            reasons.append("Light smoke outdoor")
        if has("steam") and has("pressure_vessel"):
            severity_hits.append("MEDIUM")
            reasons.append("Steam from pressure vessel")
        if has("heat_haze"):
            severity_hits.append("MEDIUM")
            reasons.append("Heat haze")
        if has("bare_hand") and has("hot_surface"):
            severity_hits.append("MEDIUM")
            reasons.append("Bare hand near hot surface")
        if has("no_helmet") or has("no_gloves"):
            severity_hits.append("MEDIUM")
            reasons.append("Missing PPE")
        if has("person") and has("flame"):
            severity_hits.append("MEDIUM")
            reasons.append("Person near flame")
        if has("structural_deform"):
            severity_hits.append("MEDIUM")
            reasons.append("Structural deformation")
        if has("weapon_like_object"):
            severity_hits.append("MEDIUM")
            reasons.append("Ambiguous weapon-like object")

        # LOW / normalizing rules
        if has("steam") and not has("pressure_vessel"):
            severity_hits.append("LOW")
            reasons.append("Steam (normal ops possible)")
        if has("heat_haze") and not (has("pressure_vessel") or has("flame")):
            severity_hits.append("LOW")
            reasons.append("Heat haze near expected source")
        if has("person_protected"):
            severity_hits.append("LOW")
            reasons.append("PPE present")
        if has("fire_extinguisher"):
            severity_hits.append("LOW")
            reasons.append("Fire extinguisher available")
        if has("alarm_light"):
            severity_hits.append("LOW")
            reasons.append("Alarm active")
        if has("sprinkler"):
            severity_hits.append("LOW")
            reasons.append("Sprinkler available")
        if has("emergency_exit"):
            severity_hits.append("LOW")
            reasons.append("Exit visible")
        if has("vehicle") and not has("flame"):
            severity_hits.append("LOW")
            reasons.append("Vehicle normal operation")

        # Default fallbacks
        if not severity_hits:
            if has("flame"):
                severity_hits.append("HIGH")
                reasons.append("Unclassified flame")
            elif has("smoke"):
                severity_hits.append("MEDIUM")
                reasons.append("Unclassified smoke")
            elif has("spark") or has("ember"):
                severity_hits.append("LOW")
                reasons.append("Unclassified ignition")
            else:
                severity_hits.append("NORMAL")
                reasons.append("No hazards detected")

        # Take worst severity, then apply mitigation
        worst = self._severity_max(*severity_hits)
        mitigated, mitigations = self._apply_mitigation(worst, present)

        # Scoring
        raw_score, score_label = self._score_from_factors(present)
        # Ensure the textual severity is at least as high as mitigated severity
        final_rank = max(SEVERITY_RANK.get(mitigated, 0), SEVERITY_RANK.get(score_label, 0))
        final_severity = SEVERITY_ORDER[final_rank]

        return {
            'present': sorted(present),
            'severity': final_severity,
            'raw_worst': worst,
            'mitigations': mitigations,
            'reasons': reasons,
            'score': raw_score,
        }

    def _get_bundled_model_path(self):
        """
        Get the path to the bundled YOLO model.
        Works for both development and PyInstaller bundled app.
        """
        # Check if running as PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            base_path = sys._MEIPASS
        else:
            # Running as script
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        model_path = os.path.join(base_path, 'models', 'yolov8n_fire.pt')
        return model_path

    def load_model(self, path):
        """
        Load YOLOv8 model from local file (100% offline).
        """
        try:
            from ultralytics import YOLO
            print(f"Loading YOLO model from: {path}")
            self.model = YOLO(path)
            self.model_loaded = True
            print(f"YOLO model loaded successfully. Classes: {self.model.names if hasattr(self.model, 'names') else 'N/A'}")
        except ImportError:
            print("Warning: ultralytics package not installed. Install with: pip install ultralytics")
            self.model_loaded = False
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            self.model_loaded = False

    def heuristic_fire_smoke(self, frame):
        """
        Fast OpenCV-based fire/smoke detection.
        Returns: confidence score (0-1)
        """
        # Fire: look for high saturation, warm colors (HSV)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_fire = np.array([0, 100, 100])
        upper_fire = np.array([40, 255, 255])
        mask_fire = cv2.inRange(hsv, lower_fire, upper_fire)
        fire_pixels = cv2.countNonZero(mask_fire)
        fire_ratio = fire_pixels / (frame.shape[0] * frame.shape[1])
        
        # Smoke: low saturation, high brightness (gray/white smoke)
        lower_smoke = np.array([0, 0, 180])
        upper_smoke = np.array([180, 60, 255])
        mask_smoke = cv2.inRange(hsv, lower_smoke, upper_smoke)
        smoke_pixels = cv2.countNonZero(mask_smoke)
        smoke_ratio = smoke_pixels / (frame.shape[0] * frame.shape[1])
        
        # Combine heuristics with adjusted weights
        # Fire is more critical, so weight it higher
        confidence = min(1.0, fire_ratio * 3 + smoke_ratio * 1.5)
        return confidence

    def yolo_detect(self, frame):
        """
        Run YOLO model on frame. Returns confidence score (0-1).
        Detects fire, smoke, flame, and potentially cigarettes.
        """
        if not self.model_loaded or self.model is None:
            return 0.0
        
        try:
            # Run inference (verbose=False to suppress output)
            results = self.model(frame, verbose=False, conf=0.25)  # 25% confidence threshold
            
            max_conf = 0.0
            detections = []

            # Only consider detections for fire-relevant classes when available
            allowed_names = {
                "fire", "smoke", "flame", "cigarette", "lighter", "match", "matches",
                "smoke_heavy", "smoke_toxic", "spark", "ember", "hot_surface", "chemical_leak",
                "steam", "heat_haze", "bare_hand", "no_helmet", "no_gloves", "person", "person_protected",
                "fire_extinguisher", "alarm_light", "sprinkler", "emergency_exit", "vehicle", "ship", "aircraft",
                "fuel_tank", "gas_cylinder", "confined_space", "flammable_liquid", "combustible_material",
                "pressure_vessel", "equipment_overheating", "structural_deform", "structural_collapse",
                "damaged_vent", "gas_leak", "electrical_arc", "explosion", "explosive_device", "firearm", "knife",
                "weapon_like_object", "fight", "person_distress", "person_rescuer", "helmet", "gloves", "ppe",
                "alarm_light_active", "sprinkler_active", "evacuation_in_progress", "hazard_contained",
                "aggressive_posture"
            }
            names = {}
            if hasattr(self.model, 'names') and isinstance(self.model.names, (dict, list)):
                # Normalize to dict index->name
                if isinstance(self.model.names, list):
                    names = {i: n for i, n in enumerate(self.model.names)}
                else:
                    names = self.model.names
            # If model doesn't include any fire-relevant class names, ignore YOLO output entirely
            if names and not any(str(n).strip().lower() in allowed_names for n in names.values()):
                return 0.0
            
            for r in results:
                if r.boxes is not None and len(r.boxes) > 0:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        class_id = int(box.cls[0])
                        
                        # Get class name
                        if names:
                            class_name = names.get(class_id, str(class_id))
                        else:
                            class_name = str(class_id)
                        
                        # Consider only fire-relevant classes
                        if str(class_name).strip().lower() in allowed_names:
                            detections.append({
                                'class': class_name,
                                'confidence': conf
                            })
                            if conf > max_conf:
                                max_conf = conf
            
            # Log detections if any found (for debugging)
            if detections and max_conf > 0.5:
                log_debug(f"YOLO detections: {detections[:3]}")  # Log top 3
            # Cache details for optional consumers
            self.last_details = {'detections': detections, 'max_conf': max_conf}
            return max_conf
            
        except Exception as e:
            log_error(f"YOLO inference error: {e}")
            return 0.0

    def detect(self, frame):
        """
        Main entry: run both heuristic and YOLO model, return max confidence.
        Combines fast heuristic with accurate YOLO detection.
        """
        h_score = self.heuristic_fire_smoke(frame)
        y_score = self.yolo_detect(frame)
        
        # Return max of both methods
        final_score = max(h_score, y_score)
        
        # Optionally build structured details if detections are cached
        details = None
        if self.last_details and isinstance(self.last_details, dict):
            details = self.detect_with_details(frame, reuse_last_yolo=True)
        
        # Debug logging for moderate+ scores to aid testing (lowered threshold)
        if final_score >= 0.2:
            try:
                log_debug(f"[VisionDetect] Heuristic={h_score:.3f}, YOLO={y_score:.3f}, Final={final_score:.3f}")
            except Exception:
                pass
        
        return final_score if details is None else details.get('final_score', final_score)

    def detect_with_details(self, frame, context=None, reuse_last_yolo=False):
        """
        Run detection and return a structured payload containing:
        {
            'final_score': float,
            'heuristic_score': float,
            'yolo_score': float,
            'detections': list[{class, confidence}],
            'threat': {severity, raw_worst, mitigations, reasons, score, present}
        }
        context: optional iterable of contextual flags (e.g., ["indoor", "confined_space"]).
        reuse_last_yolo: when True, uses cached detections from prior yolo_detect call (avoids double inference).
        """
        h_score = self.heuristic_fire_smoke(frame)
        detections = []
        y_score = 0.0

        if reuse_last_yolo and self.last_details:
            detections = self.last_details.get('detections', [])
            y_score = float(self.last_details.get('max_conf', 0.0))
        else:
            y_score = self.yolo_detect(frame)
            if self.last_details:
                detections = self.last_details.get('detections', [])

        threat = self._classify_detections(detections, context=context)
        final_score = max(h_score, y_score)

        # Cache details for external consumers
        self.last_details = {
            'detections': detections,
            'max_conf': y_score,
            'threat': threat,
            'heuristic_score': h_score,
            'final_score': final_score,
        }

        return {
            'final_score': final_score,
            'heuristic_score': h_score,
            'yolo_score': y_score,
            'detections': detections,
            'threat': threat,
        }
