# RTSP Simulator Architecture

**Version:** 1.0

## Overview
The RTSP simulator streams a local video file to EmberEye (or any RTSP client) using FFmpeg, providing a realistic camera-like feed for testing.

## Components
- **rtsp_camera_simulator.py**
  - Python wrapper that builds and runs the FFmpeg command.
  - Handles input video validation and configuration options.
- **FFmpeg process**
  - Reads the video file and encodes to H.264 (low-latency settings).
  - Pushes the RTSP stream to the local RTSP server.
- **MediaMTX (RTSP server)**
  - Accepts the FFmpeg push stream.
  - Serves RTSP clients (EmberEye, VLC, ffplay, etc.).

## Data Flow
```
Video File -> rtsp_camera_simulator.py -> FFmpeg -> MediaMTX -> RTSP Client (EmberEye)
```

## Runtime Ports
- **RTSP:** 8554/tcp
- **RTP/RTCP:** 8000/udp, 8001/udp

## Default Stream URL
```
rtsp://localhost:8554/camera1
```

## Key Settings (Defaults)
- **Codec:** H.264
- **Preset:** ultrafast
- **Tune:** zerolatency
- **Bitrate:** 2000k
- **Transport:** TCP

## Notes
- The simulator loops the video indefinitely.
- Multiple simulators can run concurrently on different ports/stream names.
