# 🎯 HYBRID DETECTION SYSTEM - IMPLEMENTATION GUIDE

**Created**: February 17, 2026  
**Status**: Ready for Integration Review  
**Target**: Multi-stream real-time fire/hazard detection with 70%+ accuracy

---

## 📁 **NEW FILES CREATED**

### 1. `embereye/core/detection_queue.py`
**Purpose**: Async frame queue and result caching

**Key Classes:**
- `DetectionResult` - Structured detection output
- `DetectionQueue` - Thread-safe queue for frame management

**Features:**
- Non-blocking frame adding (backpressure handling)
- Result caching with bounded size
- Per-stream statistics tracking
- Global singleton instance

---

### 2. `embereye/core/hybrid_detector.py`
**Purpose**: Two-stage detection pipeline

**Key Classes:**
- `HybridDetector` - Main detection engine

**Detection Pipeline:**
```
Frame Input
    ↓
[Stage 1] Heuristic Detection (<1ms)
    - Fire colors: Orange/Red (HSV Hue 0-40°)
    - Smoke colors: Gray/White (low saturation, high brightness)
    - Returns: 0-1 confidence score
    ↓
[Route Decision]
    - If score < 0.20: Skip YOLO (obvious non-hazard)
    - If score >= 0.20: Queue for YOLO validation
    ↓
[Stage 2] YOLO Inference (800-1200ms, async)
    - Runs in background worker thread
    - Detects 41 hazard classes
    - Returns: Detection result when ready
    ↓
[Confidence Mapping]
    - >= 0.70: CONFIRMED (red alert)
    - 0.50-0.70: POSSIBLE (orange warning)
    - < 0.50: LOW (ignore)
```

**Key Methods:**
- `heuristic_detect(frame)` - Fast color-based detection
- `detect_frame(frame)` - Main entry point for video workers
- `process_queued_frame(metadata)` - YOLO processing (worker thread)
- `map_to_confidence_level(score)` - Status mapping

---

### 3. `embtareye/core/detection_worker.py`
**Purpose**: Background worker thread for YOLO processing

**Key Classes:**
- `DetectionWorker` - Threading worker

**Features:**
- Runs in separate thread (never blocks video capture)
- Async frame processing from shared queue
- Result callbacks for UI updates
- Graceful shutdown and pause/resume
- Built-in statistics tracking

**Key Methods:**
- `run()` - Main worker loop
- `stop()` - Signal graceful shutdown
- `pause() / resume()` - Pause processing
- `get_stats()` - Worker and queue statistics

---

## 🔌 **INTEGRATION POINTS**

### A. Replace VisionDetector with HybridDetector in VideoWorker

**Current** (video_worker.py):
```python
from embereye.core.vision_detector import VisionDetector

class VideoWorker(QObject):
    def __init__(self, stream_id, ...):
        self.vision_detector = VisionDetector()  # ← OLD
```

**New**:
```python
from embereye.core.hybrid_detector import HybridDetector
from embereye.core.detection_worker import get_detection_worker

class VideoWorker(QObject):
    def __init__(self, stream_id, ...):
        self.detector = HybridDetector(stream_id=stream_id)  # ← NEW
        # Start global worker thread (once per app)
        if not hasattr(self.__class__, '_worker_started'):
            get_detection_worker(result_callback=self.on_detection_result)
            self.__class__._worker_started = True
```

### B. Update Frame Processing Loop

**Current**:
```python
def process_frame(self, frame):
    score = self.vision_detector.detect(frame)
    # Frame processed synchronously
    self.emit_anomaly(frame, score)
```

**New**:
```python
def process_frame(self, frame):
    # Stage 1: Fast heuristic (non-blocking)
    heuristic_score, cached_result = self.detector.detect_frame(frame)
    
    # Display frame with current status
    if cached_result:
        # Previous frame's YOLO result is ready
        self.display_frame_with_result(frame, cached_result)
    else:
        # Show frame with heuristic status (waiting for YOLO)
        self.display_frame_with_status(frame, heuristic_score)
    
    # Frame return immediately (Stage 2 happens async)

def on_detection_result(self, result: DetectionResult):
    """Callback when YOLO result is ready"""
    if result.stream_id != self.stream_id:
        return  # Result for different stream
    
    # Update UI with YOLO result
    if result.status == "CONFIRMED":
        self.highlight_frame_red(result)
        self.trigger_alert(result)  # Email, siren, etc.
    elif result.status == "POSSIBLE":
        self.highlight_frame_orange(result)
        self.log_warning(result)
```

### C. Update Video Display Widget

**Add visual feedback for confidence levels:**

```python
class VideoDisplayWidget(QFrame):
    def highlight_frame(self, status: str, class_name: str, confidence: float):
        """
        Highlight frame border based on detection status
        
        status: "CONFIRMED" | "POSSIBLE" | "LOW"
        """
        colors = {
            "CONFIRMED": "#FF0000",  # Red
            "POSSIBLE": "#FFA500",   # Orange
            "LOW": "#808080"         # Gray
        }
        
        color = colors.get(status, "gray")
        border_width = 5 if status != "LOW" else 1
        
        # Update frame border
        self.setStyleSheet(f"""
            QFrame {{
                border: {border_width}px solid {color};
                border-radius: 4px;
            }}
        """)
        
        # Display detection text overlay
        if status != "LOW":
            self.show_detection_label(f"{status}: {class_name} ({confidence:.0%})")
```

### D. Update Fusion Overlay

**Enhanced fusion scoring with YOLO classes:**

```python
def update_fusion_score(self, result: DetectionResult):
    """
    Fusion scoring now incorporates YOLO detection classes
    
    Example:
    - PERSON_IN_DISTRESS detected: weight +0.95
    - PERSON_WITHOUT_SAFETY_WEAR detected: weight +0.60
    - SMOKE_WITH_FIRE detected: weight +0.90
    """
    
    # Base fusion scoring (thermal + gas + flame still intact)
    base_score = self.sensor_fusion.fuse(...)
    
    # Enhance with YOLO class confidence
    if result.status == "CONFIRMED":
        # Use class priority from HybridDetector
        class_weight = detector.class_priority.get(result.primary_class, 0.5)
        enhanced_score = base_score * (1 + class_weight * 0.3)  # 30% boost
    elif result.status == "POSSIBLE":
        class_weight = detector.class_priority.get(result.primary_class, 0.5)
        enhanced_score = base_score * (1 + class_weight * 0.15)  # 15% boost
    else:
        enhanced_score = base_score
    
    self.fusion_overlay.update(enhanced_score)
```

### E. Shutdown Handling

**Update main window shutdown:**

```python
def closeEvent(self, event):
    # ... existing shutdown code ...
    
    # Stop detection worker
    from embereye.core.detection_worker import stop_detection_worker
    stop_detection_worker()
    
    event.accept()
```

---

## 📊 **DETECTION RESULT STRUCTURE**

Every YOLO result includes:

```python
DetectionResult(
    frame_id="stream_1-245",              # Unique identifier
    stream_id="stream_1",                 # Which stream
    status="CONFIRMED",                   # CONFIRMED | POSSIBLE | LOW
    confidence=0.78,                      # Highest detection confidence
    primary_class="SMOKE_WITH_FIRE",      # Top detected class
    
    detections=[                          # All detected objects
        {
            'class': 'SMOKE_WITH_FIRE',
            'confidence': 0.78,
            'bbox': [100, 120, 450, 380]  # [x1, y1, x2, y2]
        },
        {
            'class': 'PERSON_IN_DISTRESS',
            'confidence': 0.62,
            'bbox': [200, 250, 350, 500]
        }
    ],
    
    yolo_latency_ms=890,                  # Time spent in YOLO
    timestamp_ms=1708158342000            # When frame was captured
)
```

---

## ⚡ **PERFORMANCE CHARACTERISTICS**

### Single Stream (30fps)

| Stage | Time | Frames Processed | Notes |
|-------|------|-----------------|-------|
| **Heuristic** | <1ms | All 30/s | Fire/smoke color check |
| **YOLO Queue** | N/A | 6-9/s | ~0.20 threshold filters 70% |
| **YOLO Inference** | 800-1200ms/image | ~1/sec | Async, doesn't block capture |
| **Total Pipeline** | ~1000ms | Full real-time | Video never waits |

### Multi-Stream (3x 30fps streams)

```
Frame Timeline (milliseconds):

Time   Stream 1         Stream 2         Stream 3         Worker Thread
----   --------         --------         --------         --------
0ms    F1 Heuristic ✓   
33ms   F2 Heuristic ✓   F1 Heuristic ✓
66ms   F3 Heuristic ✓   F2 Heuristic ✓   F1 Heuristic ✓
99ms   F4 Heuristic ✓   F3 Heuristic ✓   F2 Heuristic ✓
...    (continue without blocking)
33ms                                                      Process S2-F1 (YOLO)
800ms                                                     S2-F1 Result → UI
900ms                                                     Process S1-F2 (YOLO)
1700ms                                                    S1-F2 Result → UI
```

**Key**: Video streams capture at full 30fps regardless of YOLO processing. YOLO queue processes ~1-2 frames/second per worker.

---

## 🎨 **VISUAL FEEDBACK EXAMPLES**

### Confidence Level Displays

```
CONFIRMED (>= 0.70)
┌─────────────────────────────────┐
│ 🔴 CONFIRMED                    │   ← Red border (5px)
│ SMOKE_WITH_FIRE: 0.78           │
│ Detected at: 156, 234           │   ← Detection stats
│ [Alert triggered]               │
└─────────────────────────────────┘

POSSIBLE (0.50-0.70)
┌─────────────────────────────────┐
│ 🟠 POSSIBLE                     │   ← Orange border (5px)
│ PERSON_IN_DISTRESS: 0.65        │
│ Detected at: 234, 156           │   ← Potential hazard
│ [Monitoring...]                 │
└─────────────────────────────────┘

LOW (< 0.50)
┌─────────────────────────────────┐
│ Stream 1                         │   ← Gray border (1px)
│ No hazards detected             │
└─────────────────────────────────┘
```

---

## 🔧 **CONFIGURATION & TUNING**

### Threshold Adjustments (in hybrid_detector.py)

```python
# Skip YOLO if heuristic is below this
HEURISTIC_THRESHOLD = 0.20

# Map YOLO confidence to levels
CONFIRMED_THRESHOLD = 0.70   # >= 0.70
POSSIBLE_THRESHOLD = 0.50    # 0.50-0.70
# < 0.50 is ignored

# Class importance (affects fusion scoring)
class_priority = {
    'PERSON_IN_DISTRESS': 0.95,  # Highest priority
    'FIRE': 0.95,
    'SMOKE_WITH_FIRE': 0.90,
    'PERSON_WITHOUT_SAFETY_WEAR': 0.60,  # Medium priority
    'HAZARD_UNSPECIFIED': 0.40  # Lowest
}
```

### Queue Limits (in detection_queue.py)

```python
# Max frames waiting for YOLO
MAX_QUEUE_SIZE = 100

# Max cached results
RESULT_CACHE_SIZE = 500

# Backpressure: drop oldest if full
detector_queue.add_frame(frame_metadata)  # Auto-drops old if full
```

---

## 📈 **MONITORING & DIAGNOSTICS**

### Access Statistics

```python
# In main window or monitoring thread
from embereye.core.detection_worker import get_detection_worker

worker = get_detection_worker()
stats = worker.get_stats()

print(f"Frames processed: {stats['frames_processed']}")
print(f"Queue depth: {stats['queue_size']}")
print(f"Avg latency: {stats['avg_inference_ms']:.0f}ms")
print(f"Model loaded: {stats['model_loaded']}")

# Reset for new baseline
worker.reset_stats()
```

### Logging Generated

```
[HybridDetector-stream_1] Loading YOLO from: models/v20260216_213235_model.pt
[HybridDetector-stream_1] ✓ Model loaded. Classes: 41
[DetectionWorker] Started
[DetectionWorker] Processed 50 frames, Avg latency: 950ms
[HybridDetector-stream_2] YOLO inference...
[Detection Result] stream_1-245: CONFIRMED SMOKE_WITH_FIRE (0.78)
[Callback] Alert triggered for stream_1
```

---

## ✅ **IMPLEMENTATION CHECKLIST**

- [ ] Copy 3 new files to `embereye/core/`:
  - [ ] `detection_queue.py`
  - [ ] `hybrid_detector.py`
  - [ ] `detection_worker.py`

- [ ] Update `video_worker.py`:
  - [ ] Replace VisionDetector import
  - [ ] Add HybridDetector initialization
  - [ ] Update process_frame() method
  - [ ] Add on_detection_result() callback

- [ ] Update `main_window.py`:
  - [ ] Add shutdown code for detection worker
  - [ ] Update any references to vision_detector

- [ ] Update UI widgets:
  - [ ] Add confidence level highlighting
  - [ ] Add detection label display
  - [ ] Update colors (red/orange/gray)

- [ ] Update fusion overlay:
  - [ ] Integrate YOLO class weights
  - [ ] Update scoring logic

- [ ] Testing:
  - [ ] Test with single stream
  - [ ] Test with 3+ streams
  - [ ] Verify no video capture lag
  - [ ] Check queue statistics

---

## 🎯 **EXPECTED OUTCOMES**

After implementation:

✅ **Accuracy**: 70%+ true positive rate for CONFIRMED detections  
✅ **Multi-class**: Detects all 41 hazard types (not just fire)  
✅ **Speed**: Heuristic processes all frames instantly (<1ms)  
✅ **Scalability**: Handles 3-10 simultaneous streams  
✅ **Non-blocking**: Video never waits for YOLO  
✅ **Informative**: Three confidence levels guide user response  
✅ **Integrated**: Works seamlessly with fusion overlay  

---

## 📋 **NEXT STEPS**

1. **Review this implementation guide** - Any questions/changes?
2. **Integrate the 3 new files** - Copy to `embereye/core/`
3. **Update video_worker.py** - Replace detection logic
4. **Update UI widgets** - Add visual feedback
5. **Test with streams** - Verify accuracy and performance
6. **Fine-tune thresholds** - Adjust based on real data

---

**Status**: ✅ Ready for Implementation  
**Do you want me to proceed with integration?**
