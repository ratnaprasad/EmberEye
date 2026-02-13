# RTSP Camera Simulator

Stream video files (MOV, MP4, AVI, etc.) via RTSP protocol for testing EmberEye camera integration.

## Features

✅ **Any Video Format** - MOV, MP4, AVI, MKV, WebM, FLV, WMV, etc.  
✅ **Infinite Loop** - Video plays continuously on repeat  
✅ **RTSP Protocol** - Standard camera protocol, works with any RTSP client  
✅ **Low Latency** - Optimized for real-time streaming  
✅ **Cross-Platform** - Windows, Linux, macOS  
✅ **Configurable** - Port, stream name, resolution, FPS  

## Requirements

### FFmpeg Installation

**Windows:**
```powershell
# Option 1: Chocolatey
choco install ffmpeg

# Option 2: Manual download
# 1. Download from https://ffmpeg.org/download.html
# 2. Extract to C:\ffmpeg
# 3. Add C:\ffmpeg\bin to PATH
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Linux (CentOS/RHEL):**
```bash
sudo yum install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### Verify Installation
```bash
ffmpeg -version
```

## Quick Start

### Automated Startup (Recommended)

**Windows:**
```batch
cd D:\EE\EmberEye\simulators\rtsp
start_camera.bat
```

**Linux/macOS:**
```bash
cd /path/to/EmberEye/simulators/rtsp
chmod +x start_camera.sh
./start_camera.sh
```

This will automatically:
1. Start MediaMTX RTSP server
2. Wait for server initialization
3. Start streaming IMG_1318.MOV to `rtsp://localhost:8554/camera1`

### Stop All Services

**Windows:**
```batch
cd D:\EE\EmberEye\simulators\rtsp
stop_camera.bat
```

**Linux/macOS:**
```bash
cd /path/to/EmberEye/simulators/rtsp
chmod +x stop_camera.sh
./stop_camera.sh
```

### Manual Python Command (Advanced)
```bash
# Start MediaMTX first
cd D:\EE\EmberEye\simulators\rtsp\mediamtx
start mediamtx.exe   # Windows
# or
./mediamtx &         # Linux/macOS

# Then start simulator
cd ..
python rtsp_camera_simulator.py --video data\IMG_1318.MOV
```

## Configuration

### Basic Usage
```bash
# Default: port 8554, stream name 'camera1'
python rtsp_camera_simulator.py --video video.mp4
```

### Custom Port
```bash
python rtsp_camera_simulator.py --video video.mov --port 8555
```

### Custom Stream Name
```bash
python rtsp_camera_simulator.py --video video.avi --name frontdoor
```

### Change Resolution
```bash
# Force 720p
python rtsp_camera_simulator.py --video video.mp4 --resolution 1280x720

# Force 1080p
python rtsp_camera_simulator.py --video video.mov --resolution 1920x1080
```

### Change FPS
```bash
# Force 30 FPS
python rtsp_camera_simulator.py --video video.mp4 --fps 30
```

### Full Customization
```bash
python rtsp_camera_simulator.py \
  --video ../data/IMG_1318.MOV \
  --port 8555 \
  --name outdoor_camera \
  --resolution 1280x720 \
  --fps 25
```

## Multiple Cameras

Run multiple simulators simultaneously on different ports:

**Windows:**
```batch
REM Terminal 1 - Camera 1
python rtsp_camera_simulator.py --video cam1.mov --port 8554 --name camera1

REM Terminal 2 - Camera 2
python rtsp_camera_simulator.py --video cam2.mp4 --port 8555 --name camera2

REM Terminal 3 - Camera 3
python rtsp_camera_simulator.py --video cam3.avi --port 8556 --name camera3
```

**Linux/macOS:**
```bash
# Run in background
python3 rtsp_camera_simulator.py --video cam1.mov --port 8554 --name camera1 &
python3 rtsp_camera_simulator.py --video cam2.mp4 --port 8555 --name camera2 &
python3 rtsp_camera_simulator.py --video cam3.avi --port 8556 --name camera3 &
```

## RTSP URLs

After starting the simulator, the RTSP URL will be:

```
rtsp://localhost:8554/camera1
```

Format: `rtsp://[host]:[port]/[stream_name]`

**Examples:**
- `rtsp://localhost:8554/camera1`
- `rtsp://127.0.0.1:8555/outdoor`
- `rtsp://192.168.1.100:8554/frontdoor`

## Usage in EmberEye

### Full Workflow

1. **Start RTSP Simulator**
   ```batch
   cd D:\EE\EmberEye\simulators\rtsp
   start_camera.bat
   ```
   - MediaMTX server starts automatically
   - Camera stream begins after 3 seconds
   - Stream URL: `rtsp://localhost:8554/camera1`

2. **Start EmberEye Field Application**
   ```batch
   cd D:\EE\EmberEye
   python embereye-field\main.py
   ```

3. **Configure in EmberEye Field**
   - Camera should already be configured as "Demo Room (Simulator)"
   - If not, add camera with:
     - Type: RTSP
     - URL: `rtsp://localhost:8554/camera1`
     - Name: Demo Room
   - Video should start playing immediately

4. **Stop All Services** (when done)
   ```batch
   cd D:\EE\EmberEye\simulators\rtsp
   stop_camera.bat
   ```

### Quick Reference

**Stream URL:** `rtsp://localhost:8554/camera1`  
**Video File:** `simulators/rtsp/data/IMG_1318.MOV`  
**Port:** 8554 (default RTSP port)  
**Stream Name:** camera1  

### Manual Configuration (if needed)

1. **Start Simulator** (see above)

2. **In EmberEye**
   - Open EmberEye Field application
   - Go to Camera Settings / Add Camera
   - Set Camera Type: `RTSP`
   - Set URL: `rtsp://localhost:8554/camera1`
   - Set Name: `Demo Room` (or any name)
   - Click `Connect` or `Test`

3. **Verify Stream**
   - Video should start playing
   - Stream loops infinitely
   - Check for any error messages

## Testing RTSP Stream

### VLC Media Player
```bash
vlc rtsp://localhost:8554/camera1
```

Or in VLC:
1. Media → Open Network Stream
2. Enter: `rtsp://localhost:8554/camera1`
3. Click Play

### FFplay (FFmpeg tool)
```bash
ffplay rtsp://localhost:8554/camera1
```

### OpenCV Python Test
```python
import cv2

cap = cv2.VideoCapture('rtsp://localhost:8554/camera1')

while True:
    ret, frame = cap.read()
    if not ret:
        break
    cv2.imshow('RTSP Stream', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
```

## Troubleshooting

### "FFmpeg not found"
**Problem:** FFmpeg not in PATH  
**Solution:** Install FFmpeg and ensure it's in system PATH

```bash
# Test FFmpeg
ffmpeg -version
```

### "Video file not found"
**Problem:** Incorrect path to video file  
**Solution:** Use absolute path or correct relative path

```bash
# Use absolute path
python rtsp_camera_simulator.py --video "D:\Videos\test.mp4"

# Or relative from rtsp folder
python rtsp_camera_simulator.py --video ..\data\IMG_1318.MOV
```

### "Connection refused" in EmberEye
**Problem:** Simulator not running or wrong URL  
**Solutions:**
1. Verify simulator is running (check terminal output)
2. Check RTSP URL format: `rtsp://localhost:8554/camera1`
3. Verify port not blocked by firewall
4. Try VLC to test stream independently

### "Stream stuttering or freezing"
**Problem:** High bitrate or CPU load  
**Solutions:**
1. Lower resolution: `--resolution 1280x720`
2. Lower FPS: `--fps 25`
3. Use smaller video file
4. Check system resources (CPU/RAM)

### Port already in use
**Problem:** Port 8554 occupied by another application  
**Solution:** Use different port

```bash
python rtsp_camera_simulator.py --video video.mp4 --port 8555
# Then use: rtsp://localhost:8555/camera1
```

## Supported Video Formats

FFmpeg supports virtually all video formats:

| Format | Extension | Notes |
|--------|-----------|-------|
| QuickTime | .mov | ✓ Native support |
| MPEG-4 | .mp4 | ✓ Most common |
| AVI | .avi | ✓ Windows standard |
| Matroska | .mkv | ✓ High quality |
| WebM | .webm | ✓ Web format |
| Flash | .flv | ✓ Legacy |
| Windows Media | .wmv | ✓ Windows |
| MPEG | .mpeg, .mpg | ✓ Standard |

**If FFmpeg can play it, the simulator can stream it!**

## Performance Tips

### Low Latency Settings (Default)
- Preset: `ultrafast`
- Tune: `zerolatency`
- Transport: `TCP`

### High Quality Settings
Modify `rtsp_camera_simulator.py`:
```python
'-preset', 'slow',  # Change from 'ultrafast'
'-b:v', '4000k',    # Change from '2000k'
```

### Bandwidth Optimization
```python
'-b:v', '1000k',    # Lower bitrate
'-bufsize', '2000k',
```

## Architecture

```
┌─────────────────────────────────────────┐
│        rtsp_camera_simulator.py         │
│  (Python wrapper for FFmpeg)            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│            FFmpeg Process                │
│  - Read video file                      │
│  - Encode H.264/AAC                     │
│  - Stream via RTSP                      │
└─────────────────┬───────────────────────┘
                  │
                  ▼ (RTSP TCP/UDP)
┌─────────────────────────────────────────┐
│         EmberEye / RTSP Client          │
│  - Connect to rtsp://localhost:8554     │
│  - Decode and display video             │
└─────────────────────────────────────────┘
```

## Advanced Usage

### Background Execution (Linux/macOS)
```bash
# Start in background with log
nohup python3 rtsp_camera_simulator.py --video video.mp4 > rtsp.log 2>&1 &

# Check process
ps aux | grep rtsp_camera

# Stop
pkill -f rtsp_camera_simulator
```

### Windows Service (Advanced)
Use NSSM (Non-Sucking Service Manager) to run as Windows service:
```powershell
# Install NSSM
choco install nssm

# Create service
nssm install RTSPCamera "C:\Python\python.exe" "D:\EE\EmberEye\simulators\rtsp\rtsp_camera_simulator.py" "--video" "..\data\IMG_1318.MOV"

# Start service
nssm start RTSPCamera
```

## File Organization

```
simulators/
├── rtsp/
│   ├── rtsp_camera_simulator.py   # Main simulator
│   ├── start_camera.bat            # Windows launcher
│   ├── start_camera.sh             # Linux/macOS launcher
│   └── README.md                   # This file
└── data/
    └── IMG_1318.MOV                # Video file to stream
```

## Future Enhancements

- [ ] Multiple video files (playlist)
- [ ] Schedule-based streaming
- [ ] Motion detection overlay
- [ ] PTZ control simulation
- [ ] Snapshot/image capture
- [ ] Stream authentication
- [ ] UDP transport option
- [ ] Multicast streaming

## License

Part of EmberEye Fire Detection System  
© 2026 EmberEye

---

**Version**: 1.0  
**Date**: January 2026  
**Author**: EmberEye Development Team
