import time
import numpy as np

class SensorFusion:
    def __init__(self, temp_threshold=40.0, gas_ppm_threshold=400, flame_active_value=1, min_sources=2, critical_temp_threshold=60.0, smoke_threshold_pct=25.0, flame_threshold_pct=25.0):
        """
        Initialize sensor fusion with thresholds.
        temp_threshold: Temperature threshold in Celsius (e.g., 40.0°C for fire detection)
        gas_ppm_threshold: Gas concentration threshold in PPM
        flame_active_value: Value indicating flame sensor activation
        min_sources: Minimum number of sensor sources required for alarm
        critical_temp_threshold: Critical temperature threshold for immediate alarm (bypasses multi-source requirement)
        smoke_threshold_pct: Smoke sensor threshold percentage (0-100)
        flame_threshold_pct: Flame analog sensor threshold percentage (0-100)
        """
        self.temp_threshold = temp_threshold
        self.gas_ppm_threshold = gas_ppm_threshold
        self.flame_active_value = flame_active_value
        self.min_sources = min_sources
        self.critical_temp_threshold = critical_temp_threshold
        self.smoke_threshold_pct = smoke_threshold_pct
        self.flame_threshold_pct = flame_threshold_pct
        self.event_log = []
        # Metrics integration
        try:
            from metrics import get_metrics
            self.metrics = get_metrics()
        except Exception:
            self.metrics = None

    def fuse(self, thermal_matrix=None, gas_ppm=None, flame=None, vision_score=None, **kwargs):
        """
        Priority-based fusion logic:
        1. Smoke (ADC1) crosses threshold → ALARM
        2. Flame (ADC2) crosses threshold → correlate with thermal
        3. Camera detects fire → correlate with sensors (priority: Flame > Thermal > Smoke)
        4. Hazardous gas detection → ALARM
        
        Accepts:
            thermal_matrix: 2D list (24x32) or None
            gas_ppm: float or None
            flame: int/bool or None (digital flame sensor)
            vision_score: float (0-1) or None
            **kwargs: smoke_pct, flame_analog_pct, adc1_raw, adc2_raw, etc.
        Returns:
            dict with alarm status, confidence, sources, and all sensor data
        """
        sources = []
        confidence = 0.0
        hot_cells = []
        thermal_max = 0.0
        alarm = False
        alarm_reason = None
        
        # Extract percentage values from kwargs
        smoke_pct = kwargs.get('smoke_pct', 0.0)
        flame_analog_pct = kwargs.get('flame_analog_pct', 0.0)
        flame_digital = kwargs.get('flame_digital', 0)
        
        # Thermal check with per-cell analysis
        thermal_detected = False
        if thermal_matrix is not None:
            arr = np.array(thermal_matrix)
            max_temp = arr.max()
            thermal_max = float(max_temp)
            if max_temp >= self.temp_threshold:
                thermal_detected = True
                sources.append('thermal')
                confidence += 0.4
                hot_cells = [(int(r), int(c)) for r, c in zip(*np.where(arr >= self.temp_threshold))]
        
        # PRIORITY 1: Smoke (ADC1) crosses threshold → IMMEDIATE ALARM
        if smoke_pct >= self.smoke_threshold_pct:
            alarm = True
            alarm_reason = f"Smoke threshold exceeded: {smoke_pct:.1f}% >= {self.smoke_threshold_pct}%"
            sources.append('smoke')
            confidence += 0.5
        
        # PRIORITY 2: Flame (ADC2 analog) + Thermal correlation
        flame_detected = flame_analog_pct >= self.flame_threshold_pct or (flame_digital == self.flame_active_value)
        if flame_detected:
            sources.append('flame')
            confidence += 0.3
            # Correlate with thermal
            if thermal_detected:
                alarm = True
                alarm_reason = f"Flame + Thermal correlation: Flame={flame_analog_pct:.1f}%, Thermal={thermal_max:.1f}°C"
                confidence += 0.3
        
        # PRIORITY 3: Camera vision detection → correlate with sensors
        if vision_score is not None and vision_score >= 0.7:
            sources.append('vision')
            confidence += 0.4
            # Correlate with sensors (priority: Flame > Thermal > Smoke)
            if flame_detected or thermal_detected or smoke_pct >= self.smoke_threshold_pct:
                alarm = True
                if not alarm_reason:
                    alarm_reason = f"Vision + Sensor correlation: Vision={vision_score:.2f}"
        
        # PRIORITY 4: Hazardous gas detection → IMMEDIATE ALARM
        if gas_ppm is not None and gas_ppm >= self.gas_ppm_threshold:
            alarm = True
            alarm_reason = f"Hazardous gas detected: {gas_ppm:.1f}ppm >= {self.gas_ppm_threshold}ppm"
            sources.append('gas')
            confidence += 0.5
        
        # Critical temperature override
        if thermal_max >= self.critical_temp_threshold:
            alarm = True
            alarm_reason = f"Critical temperature: {thermal_max:.1f}°C >= {self.critical_temp_threshold}°C"
            confidence = 1.0
        
        # Record metrics
        if self.metrics:
            fusion_start = time.time()
        
        # Log event
        self.event_log.append({
            'timestamp': time.time(),
            'alarm': alarm,
            'confidence': confidence,
            'sources': sources,
            'hot_cells': len(hot_cells),
            'reason': alarm_reason
        })
        
        # Build result with all sensor data
        result = {
            'alarm': alarm,
            'alarm_reason': alarm_reason,
            'confidence': confidence, 
            'sources': sources,
            'hot_cells': hot_cells,
            'thermal_max': thermal_max,
            'gas_ppm': gas_ppm if gas_ppm is not None else 0.0,
            'smoke_pct': smoke_pct,
            'flame_analog_pct': flame_analog_pct,
            'flame_digital': flame_digital
        }
        
        # Include any additional sensor data passed via kwargs
        result.update(kwargs)
        
        # Record fusion metrics
        if self.metrics:
            fusion_latency = (time.time() - fusion_start) * 1000
            self.metrics.record_fusion(alarm, fusion_latency)
        
        return result

    def get_event_log(self):
        return self.event_log
