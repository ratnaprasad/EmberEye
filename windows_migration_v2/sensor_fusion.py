import time
import numpy as np

class SensorFusion:
    def __init__(self, temp_threshold=160, gas_ppm_threshold=400, flame_active_value=1, min_sources=2):
        """
        Initialize sensor fusion with thresholds.
        temp_threshold: Temperature threshold in sensor units (0-255 scale, where ~160 = 40°C)
        gas_ppm_threshold: Gas concentration threshold in PPM
        flame_active_value: Value indicating flame sensor activation
        min_sources: Minimum number of sensor sources required for alarm
        """
        self.temp_threshold = temp_threshold
        self.gas_ppm_threshold = gas_ppm_threshold
        self.flame_active_value = flame_active_value
        self.min_sources = min_sources
        self.event_log = []

    def fuse(self, thermal_matrix=None, gas_ppm=None, flame=None, vision_score=None, **kwargs):
        """
        Accepts:
            thermal_matrix: 2D list (24x32) or None
            gas_ppm: float or None
            flame: int/bool or None
            vision_score: float (0-1) or None
            **kwargs: Additional sensor data (adc1_raw, adc2_raw, smoke_level, etc.)
        Returns:
            dict: {
                'alarm': bool, 
                'confidence': float, 
                'sources': [list],
                'hot_cells': [(row, col), ...] - thermal grid cells exceeding threshold,
                'thermal_max': float - maximum temperature value,
                'gas_ppm': float - gas concentration,
                ... additional sensor readings from kwargs
            }
        """
        sources = []
        confidence = 0.0
        hot_cells = []
        thermal_max = 0.0
        
        # Thermal check with per-cell analysis
        if thermal_matrix is not None:
            arr = np.array(thermal_matrix)
            max_temp = arr.max()
            thermal_max = float(max_temp)
            if max_temp >= self.temp_threshold:
                sources.append('thermal')
                confidence += 0.4
                # Identify individual hot cells
                hot_cells = [(int(r), int(c)) for r, c in zip(*np.where(arr >= self.temp_threshold))]
        
        # Gas check
        if gas_ppm is not None and gas_ppm >= self.gas_ppm_threshold:
            sources.append('gas')
            confidence += 0.3
        
        # Flame check
        if flame is not None and flame == self.flame_active_value:
            sources.append('flame')
            confidence += 0.2
        
        # Vision check
        if vision_score is not None and vision_score >= 0.7:
            sources.append('vision')
            confidence += 0.5
        
        # Consensus: alarm if enough sources or high confidence
        alarm = (len(sources) >= self.min_sources) or (confidence >= 0.7)
        
        # Log event
        self.event_log.append({
            'timestamp': time.time(),
            'alarm': alarm,
            'confidence': confidence,
            'sources': sources,
            'hot_cells': len(hot_cells)
        })
        
        # Build result with all sensor data
        result = {
            'alarm': alarm, 
            'confidence': confidence, 
            'sources': sources,
            'hot_cells': hot_cells,
            'thermal_max': thermal_max,
            'gas_ppm': gas_ppm if gas_ppm is not None else 0.0
        }
        
        # Include any additional sensor data passed via kwargs
        result.update(kwargs)
        
        return result

    def get_event_log(self):
        return self.event_log
