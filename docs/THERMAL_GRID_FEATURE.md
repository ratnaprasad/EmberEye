# Thermal Grid Overlay Feature

## Overview
The Thermal Grid Overlay feature provides selective visualization of thermal anomalies detected by the sensor fusion system. Instead of overlaying the entire thermal image on the video feed, this feature highlights only the specific grid cells where fire or elevated temperatures have been detected.

## Key Features

### 1. Selective Grid Cell Highlighting
- Only grid cells exceeding the temperature threshold are highlighted
- Non-threatening areas remain unobstructed for clear video visibility
- Real-time updates as sensor data is received

### 2. Configurable Grid Parameters
- **Grid Dimensions**: Adjustable rows (default: 24) and columns (default: 32) to match thermal sensor resolution
- **Cell Fill Color**: Semi-transparent color for detected hot cells (default: red with 180 alpha)
- **Border Color**: Outline color for grid cells (default: yellow with 200 alpha)
- **Border Width**: Thickness of cell borders (default: 2 pixels)
- **Temperature Threshold**: Minimum temperature to trigger cell highlighting (default: 160 units ≈ 40°C)

### 3. Integration with Sensor Fusion
- Leverages multi-sensor fusion (thermal + gas + flame + vision)
- Per-cell thermal analysis identifies specific hot spots
- Fusion confidence scoring determines alarm state
- Hot cells list passed from fusion engine to video widget

## Architecture

### Component Flow
```
TCP Sensor Data → Sensor Fusion → Hot Cells Detection → Video Widget Overlay
                       ↓
                 Alarm Status
```

### Key Components

#### 1. `sensor_fusion.py`
- **Purpose**: Multi-sensor data fusion and hot cell detection
- **Key Method**: `fuse(thermal_matrix, gas_ppm, flame, vision_score)`
  - Returns: `{'alarm': bool, 'confidence': float, 'sources': [], 'hot_cells': [(row, col), ...]}`
- **Per-Cell Analysis**: Uses `np.where(arr >= threshold)` to identify cells exceeding temperature threshold
- **Threshold**: Default 160 units (0-255 scale, where ~160 ≈ 40°C)

#### 2. `video_widget.py`
- **Purpose**: Display video feed with selective thermal grid overlay
- **Key Attributes**:
  - `hot_cells`: List of (row, col) tuples for detected hot cells
  - `thermal_grid_enabled`: Enable/disable overlay
  - `thermal_grid_rows/cols`: Grid dimensions
  - `thermal_grid_color`: Cell fill color
  - `thermal_grid_border`: Border color
- **Key Methods**:
  - `set_hot_cells(hot_cells)`: Update hot cells from fusion
  - `_redraw_with_grid()`: Render grid cells on video frame
  - `update_frame(pixmap)`: Apply overlay on each video frame update

#### 3. `main_window.py`
- **Purpose**: Coordinate TCP data, fusion, and widget updates
- **Key Method**: `handle_tcp_packet(packet)`
  - Extracts thermal matrix from `#frame` packets
  - Runs fusion with thermal + gas + flame data
  - Routes hot_cells to specific VideoWidget by loc_id
  - Updates alarm status and grid overlay

#### 4. `thermal_grid_config.py`
- **Purpose**: Configuration dialog for thermal grid settings
- **Features**:
  - Enable/disable thermal grid overlay
  - Adjust grid dimensions and appearance
  - Set temperature threshold
  - Real-time preview with "Apply" button
  - Settings persisted across all video widgets

## Usage

### 1. Enable Thermal Grid Overlay
1. Open Settings menu (top-right toolbar button)
2. Select "Thermal Grid Settings..."
3. Check "Enable Thermal Grid Overlay"
4. Click "Apply" or "OK"

### 2. Configure Grid Appearance
- **Cell Color**: Click color button to open picker, adjust RGBA values
- **Border Color**: Customize outline color for grid cells
- **Border Width**: Adjust thickness (1-10 pixels)

### 3. Adjust Detection Sensitivity
- **Temperature Threshold**: Increase to reduce false positives, decrease for earlier detection
- Default: 160 units (≈ 40°C in 0-255 scale)
- Recommended range: 140-200 units (35-50°C)

### 4. Testing with Simulator
```bash
# Start TCP sensor simulator with hot spots
python tcp_sensor_simulator.py --host 127.0.0.1 --port 9000 --loc-id "default room"
```
- Simulator generates 2-4 random hot spots per frame (200-255 units = 50-70°C)
- Hot cells highlighted in red with yellow borders on video feed

## Technical Details

### Coordinate System
- **Thermal Grid**: 24 rows × 32 columns (768 cells total)
- **Cell Indexing**: `(row, col)` where row ∈ [0, 23], col ∈ [0, 31]
- **Pixel Mapping**: 
  - `cell_width = video_width / cols`
  - `cell_height = video_height / rows`
  - `x = col * cell_width`
  - `y = row * cell_height`

### Temperature Scale
The thermal sensor outputs 8-bit values (0-255):
- **0**: Minimum temperature (typically 0°C or ambient)
- **127**: Mid-range (~30-35°C)
- **160**: Threshold (~40°C) - detection trigger
- **200-255**: High temperature (~50-70°C) - likely fire

### Drawing Algorithm
```python
# For each hot cell (row, col):
x = int(col * cell_width)
y = int(row * cell_height)
w = int(cell_width)
h = int(cell_height)

# Fill cell with semi-transparent color
painter.fillRect(x, y, w, h, cell_color)

# Draw border
painter.setPen(border_color, border_width)
painter.drawRect(x, y, w, h)
```

### Performance Optimization
- Grid overlay only drawn when `hot_cells` list is non-empty
- Redraw triggered only on hot cell changes or new video frames
- QPainter operations are hardware-accelerated
- No unnecessary full-image processing

## Configuration Persistence
Settings are applied to all video widgets in real-time:
```python
def apply_thermal_grid_settings(self, settings):
    # Update sensor fusion threshold
    self.sensor_fusion.temp_threshold = settings['temp_threshold']
    
    # Update all video widgets
    for widget in self.video_widgets.values():
        widget.thermal_grid_enabled = settings['enabled']
        widget.thermal_grid_rows = settings['rows']
        widget.thermal_grid_cols = settings['cols']
        widget.thermal_grid_color = settings['cell_color']
        widget.thermal_grid_border = settings['border_color']
```

## Troubleshooting

### Hot Cells Not Appearing
- Check if thermal grid is enabled in settings
- Verify temperature threshold is not too high
- Confirm TCP sensor data is being received (check console logs)
- Ensure sensor fusion is running (`fusion_result` should contain `hot_cells` key)

### Grid Misaligned
- Verify grid dimensions match thermal sensor resolution (24×32)
- Check if video aspect ratio is being preserved
- Ensure video widget is properly sized

### Performance Issues
- Reduce number of simultaneous video streams
- Increase thermal data interval (reduce update frequency)
- Lower video resolution

## Future Enhancements
- [ ] Color-coded severity levels (yellow/orange/red based on temperature)
- [ ] Adjustable cell opacity based on temperature intensity
- [ ] Historical hot cell tracking with decay animation
- [ ] Export hot cell data for analysis
- [ ] Multi-level thresholds (warning/critical/emergency)
- [ ] Cell-level tooltips showing exact temperature
