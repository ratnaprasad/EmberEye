"""
Incidents Module for EmberEye Field.
Thermal vision analysis, ROI extraction, incident detection, and YOLO training.
"""

import cv2
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import os
import json

@dataclass
class IncidentRecord:
    """Record of a detected incident."""
    timestamp: datetime
    incident_type: str  # 'temperature', 'smoke', 'flame', 'gas', 'motion'
    severity: str  # 'low', 'medium', 'high', 'critical'
    location: str
    description: str
    sensor_values: Dict = field(default_factory=dict)
    frame_path: Optional[str] = None
    roi_coords: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'incident_type': self.incident_type,
            'severity': self.severity,
            'location': self.location,
            'description': self.description,
            'sensor_values': self.sensor_values,
            'frame_path': self.frame_path,
            'roi_coords': self.roi_coords
        }

class ThermalROIExtractor:
    """Extract Regions of Interest from thermal frames."""
    
    def __init__(self, temp_threshold=40.0, min_area=100):
        self.temp_threshold = temp_threshold
        self.min_area = min_area
    
    def extract_hotspots(self, thermal_frame: np.ndarray, temperature_matrix: np.ndarray):
        """
        Extract hot regions from thermal frame.
        Returns list of (x, y, w, h, max_temp) tuples.
        """
        hotspots = []
        
        # Create binary mask of regions above threshold
        mask = (temperature_matrix > self.temp_threshold).astype(np.uint8) * 255
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.min_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # Get max temperature in this ROI
            roi_temps = temperature_matrix[y:y+h, x:x+w]
            max_temp = np.max(roi_temps)
            
            hotspots.append((x, y, w, h, max_temp))
        
        return hotspots
    
    def extract_roi_image(self, frame: np.ndarray, x: int, y: int, w: int, h: int):
        """Extract ROI image from frame."""
        return frame[y:y+h, x:x+w].copy()

class IncidentsManager:
    """Manage incident records with persistence."""
    
    def __init__(self, storage_file="incidents.json"):
        self.storage_file = storage_file
        self.incidents: List[IncidentRecord] = []
        self.load_incidents()
    
    def add_incident(self, incident: IncidentRecord):
        """Add new incident record."""
        self.incidents.append(incident)
        self.save_incidents()
    
    def get_recent_incidents(self, count=50) -> List[IncidentRecord]:
        """Get most recent incidents."""
        return sorted(self.incidents, key=lambda x: x.timestamp, reverse=True)[:count]
    
    def save_incidents(self):
        """Save incidents to JSON file."""
        try:
            data = [i.to_dict() for i in self.incidents]
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[INCIDENTS] Error saving: {e}")
    
    def load_incidents(self):
        """Load incidents from JSON file."""
        if not os.path.exists(self.storage_file):
            return
        
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
            
            self.incidents = []
            for item in data:
                item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                self.incidents.append(IncidentRecord(**item))
        except Exception as e:
            print(f"[INCIDENTS] Error loading: {e}")

class ThermalVisionAnalyzer:
    """Analyze thermal vision data for incidents."""
    
    def __init__(self):
        self.roi_extractor = ThermalROIExtractor()
        self.baseline_temps = {}  # location -> baseline_temp
    
    def analyze_frame(self, frame: np.ndarray, temperature_matrix: np.ndarray, 
                     location: str) -> List[IncidentRecord]:
        """
        Analyze thermal frame for incidents.
        Returns list of detected incidents.
        """
        incidents = []
        
        # Extract hotspots
        hotspots = self.roi_extractor.extract_hotspots(frame, temperature_matrix)
        
        for x, y, w, h, max_temp in hotspots:
            # Determine severity
            if max_temp > 80:
                severity = 'critical'
            elif max_temp > 60:
                severity = 'high'
            elif max_temp > 50:
                severity = 'medium'
            else:
                severity = 'low'
            
            incident = IncidentRecord(
                timestamp=datetime.now(),
                incident_type='temperature',
                severity=severity,
                location=location,
                description=f"High temperature detected: {max_temp:.1f}°C",
                sensor_values={'temperature': max_temp, 'area': w*h},
                roi_coords=(x, y, w, h)
            )
            incidents.append(incident)
        
        return incidents
