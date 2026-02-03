#!/usr/bin/env python3
"""
Incident Exporter for EmberEye Field Edition

Packages detected fire/smoke incidents with frames, detections, and metadata into 
exportable ZIP bundles for transfer to EmberEye Studio for review and retraining.

Features:
- ZIP bundling with frame sequences
- Metadata JSON with detection metadata
- Optional compression and encryption
- Batch export with progress tracking
"""

import os
import json
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class IncidentExportMetadata:
    """Metadata for a single incident export."""
    
    def __init__(self, 
                 incident_id: str,
                 location: str,
                 timestamp: str,
                 duration_seconds: float,
                 detection_count: int,
                 incident_type: str = "fire_smoke",
                 severity: str = "medium",
                 frame_count: int = 0,
                 detector_version: str = "unknown"):
        self.incident_id = incident_id
        self.location = location
        self.timestamp = timestamp
        self.duration_seconds = duration_seconds
        self.detection_count = detection_count
        self.incident_type = incident_type
        self.severity = severity
        self.frame_count = frame_count
        self.detector_version = detector_version
        self.export_timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'incident_id': self.incident_id,
            'location': self.location,
            'timestamp': self.timestamp,
            'duration_seconds': self.duration_seconds,
            'detection_count': self.detection_count,
            'incident_type': self.incident_type,
            'severity': self.severity,
            'frame_count': self.frame_count,
            'detector_version': self.detector_version,
            'export_timestamp': self.export_timestamp
        }


class DetectionFrame:
    """Single frame with detections."""
    
    def __init__(self,
                 frame_path: str,
                 timestamp: str,
                 detections: List[Dict],
                 frame_index: int = 0):
        self.frame_path = frame_path
        self.timestamp = timestamp
        self.detections = detections  # List of {class: str, confidence: float, bbox: [x,y,w,h]}
        self.frame_index = frame_index
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'frame_index': self.frame_index,
            'timestamp': self.timestamp,
            'detection_count': len(self.detections),
            'detections': self.detections,
            'filename': os.path.basename(self.frame_path)
        }


class IncidentExporter:
    """Export incident bundles for transfer to Studio."""
    
    def __init__(self, export_root_dir: str = None, compression_level: int = 6):
        """
        Initialize exporter.
        
        Args:
            export_root_dir: Root directory for exports (default: ./exports)
            compression_level: ZIP compression level 0-9 (default: 6)
        """
        if export_root_dir is None:
            export_root_dir = os.path.join(os.path.dirname(__file__), '..', 'exports')
        
        self.export_root_dir = export_root_dir
        self.compression_level = compression_level
        
        # Ensure export directory exists
        os.makedirs(self.export_root_dir, exist_ok=True)
        
        logger.info(f"[EMBERSYNC] IncidentExporter initialized: {self.export_root_dir}")
    
    def create_incident_bundle(self,
                              incident_id: str,
                              location: str,
                              timestamp: str,
                              frame_paths: List[str],
                              detection_frames: List[DetectionFrame],
                              metadata: IncidentExportMetadata) -> str:
        """
        Create a ZIP bundle containing frames and metadata for export.
        
        Args:
            incident_id: Unique incident identifier
            location: Location name (e.g., "Building A - Room 201")
            timestamp: ISO format timestamp of incident start
            frame_paths: List of frame file paths to include
            detection_frames: List of DetectionFrame objects with metadata
            metadata: IncidentExportMetadata object
        
        Returns:
            Path to created ZIP file
        """
        try:
            # Create incident directory
            incident_dir = os.path.join(self.export_root_dir, f"incident_{incident_id}")
            os.makedirs(incident_dir, exist_ok=True)
            
            # Create frames subdirectory
            frames_dir = os.path.join(incident_dir, 'frames')
            os.makedirs(frames_dir, exist_ok=True)
            
            # Copy frames
            copied_frames = []
            for i, frame_path in enumerate(frame_paths):
                if os.path.exists(frame_path):
                    filename = f"frame_{i:04d}.png"
                    dest_path = os.path.join(frames_dir, filename)
                    shutil.copy2(frame_path, dest_path)
                    copied_frames.append(filename)
                    logger.debug(f"[EMBERSYNC] Copied frame: {filename}")
            
            # Create detections metadata JSON
            detections_data = {
                'metadata': metadata.to_dict(),
                'frames': [df.to_dict() for df in detection_frames]
            }
            
            metadata_path = os.path.join(incident_dir, 'detections.json')
            with open(metadata_path, 'w') as f:
                json.dump(detections_data, f, indent=2)
            
            logger.info(f"[EMBERSYNC] Created metadata: {len(detections_data['frames'])} frames")
            
            # Create README
            readme_path = os.path.join(incident_dir, 'README.md')
            self._write_readme(readme_path, incident_id, location, timestamp, len(frame_paths))
            
            # Create ZIP bundle
            zip_filename = f"incident_{incident_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_path = os.path.join(self.export_root_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, 
                               compresslevel=self.compression_level) as zipf:
                # Add frames
                for frame_file in os.listdir(frames_dir):
                    frame_full_path = os.path.join(frames_dir, frame_file)
                    arcname = os.path.join('frames', frame_file)
                    zipf.write(frame_full_path, arcname)
                
                # Add metadata
                zipf.write(metadata_path, 'detections.json')
                zipf.write(readme_path, 'README.md')
            
            logger.info(f"[EMBERSYNC] ✅ Bundle created: {zip_filename}")
            logger.info(f"[EMBERSYNC]   Frames: {len(copied_frames)}")
            logger.info(f"[EMBERSYNC]   Size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")
            
            return zip_path
        
        except Exception as e:
            logger.error(f"[EMBERSYNC] ❌ Bundle creation failed: {e}")
            raise
    
    def _write_readme(self, path: str, incident_id: str, location: str, 
                     timestamp: str, frame_count: int):
        """Write README.md for bundle documentation."""
        content = f"""# Incident Export Bundle

**Incident ID:** {incident_id}  
**Location:** {location}  
**Start Time:** {timestamp}  
**Frames:** {frame_count}  
**Export Date:** {datetime.now().isoformat()}  

## Contents

- `frames/` - Sequence of PNG frames with detections
- `detections.json` - Metadata including detection coordinates and confidence scores

## Usage in EmberEye Studio

1. Import this bundle in Aviary (Review Interface)
2. Review detected incidents frame-by-frame
3. Validate detections and add human feedback
4. Export to golden dataset for model retraining

## Format

Each frame is named `frame_XXXX.png` in chronological order.

Detection metadata includes:
- Timestamp for each frame
- Class predictions (fire, smoke, etc.)
- Confidence scores (0.0-1.0)
- Bounding box coordinates [x, y, w, h]

"""
        with open(path, 'w') as f:
            f.write(content)
    
    def export_batch(self, incidents: List[Tuple]) -> List[str]:
        """
        Export multiple incidents in batch.
        
        Args:
            incidents: List of tuples: (incident_id, location, timestamp, 
                                       frame_paths, detection_frames, metadata)
        
        Returns:
            List of created ZIP file paths
        """
        exported = []
        for i, incident_data in enumerate(incidents):
            try:
                incident_id, location, timestamp, frames, detections, meta = incident_data
                zip_path = self.create_incident_bundle(
                    incident_id, location, timestamp, frames, detections, meta
                )
                exported.append(zip_path)
                logger.info(f"[EMBERSYNC] [{i+1}/{len(incidents)}] Exported: {incident_id}")
            except Exception as e:
                logger.error(f"[EMBERSYNC] Failed to export incident {i}: {e}")
                continue
        
        return exported
    
    def list_exported_bundles(self) -> List[Dict]:
        """
        List all exported incident bundles.
        
        Returns:
            List of dicts with bundle info {filename, path, size_mb, created}
        """
        bundles = []
        for filename in os.listdir(self.export_root_dir):
            if filename.endswith('.zip'):
                full_path = os.path.join(self.export_root_dir, filename)
                size_mb = os.path.getsize(full_path) / (1024*1024)
                mtime = os.path.getmtime(full_path)
                created = datetime.fromtimestamp(mtime).isoformat()
                
                bundles.append({
                    'filename': filename,
                    'path': full_path,
                    'size_mb': round(size_mb, 2),
                    'created': created
                })
        
        return sorted(bundles, key=lambda x: x['created'], reverse=True)
    
    def delete_bundle(self, bundle_filename: str) -> bool:
        """Delete an exported bundle."""
        try:
            bundle_path = os.path.join(self.export_root_dir, bundle_filename)
            if os.path.exists(bundle_path):
                os.remove(bundle_path)
                logger.info(f"[EMBERSYNC] Deleted bundle: {bundle_filename}")
                return True
            return False
        except Exception as e:
            logger.error(f"[EMBERSYNC] Failed to delete bundle: {e}")
            return False
    
    def cleanup_old_exports(self, keep_count: int = 50) -> int:
        """
        Clean up old exported bundles, keeping only the most recent.
        
        Args:
            keep_count: Number of recent bundles to keep
        
        Returns:
            Number of bundles deleted
        """
        bundles = self.list_exported_bundles()
        deleted_count = 0
        
        for bundle in bundles[keep_count:]:
            try:
                os.remove(bundle['path'])
                deleted_count += 1
            except Exception as e:
                logger.warning(f"[EMBERSYNC] Failed to delete old bundle: {e}")
        
        if deleted_count > 0:
            logger.info(f"[EMBERSYNC] Cleaned up {deleted_count} old bundles")
        
        return deleted_count


# Example usage (for testing)
if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Initialize exporter
    exporter = IncidentExporter()
    
    # Create sample metadata
    metadata = IncidentExportMetadata(
        incident_id='incident_001',
        location='Building A - Room 201',
        timestamp=datetime.now().isoformat(),
        duration_seconds=45.2,
        detection_count=12,
        severity='high',
        frame_count=45
    )
    
    print("✅ IncidentExporter initialized")
    print(f"   Export dir: {exporter.export_root_dir}")
    print(f"   Metadata sample: {metadata.to_dict()}")
