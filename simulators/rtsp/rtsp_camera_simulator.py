#!/usr/bin/env python3
"""
RTSP Camera Simulator v1.0

Streams video files (MOV, MP4, AVI, etc.) via RTSP protocol using FFmpeg.
Can be configured as a camera source in EmberEye or any RTSP-compatible application.

Features:
- Infinite loop playback
- Any video format supported by FFmpeg (MOV, MP4, AVI, MKV, etc.)
- Configurable RTSP URL, port, and stream name
- Cross-platform (Windows, Linux, macOS)
- Multiple simultaneous streams support

Requirements:
- FFmpeg must be installed and accessible in PATH

Author: EmberEye System
Date: January 2026
"""

import subprocess
import sys
import os
import argparse
import time
import signal
from pathlib import Path
from typing import Optional


class RTSPCameraSimulator:
    """FFmpeg-based RTSP video streaming simulator."""
    
    def __init__(self, video_file: str, rtsp_port: int = 8554, 
                 stream_name: str = "camera1", fps: Optional[int] = None,
                 resolution: Optional[str] = None):
        self.video_file = Path(video_file)
        self.rtsp_port = rtsp_port
        self.stream_name = stream_name
        self.fps = fps
        self.resolution = resolution
        self.process: Optional[subprocess.Popen] = None
        
        # Construct RTSP URL
        self.rtsp_url = f"rtsp://localhost:{rtsp_port}/{stream_name}"
        
    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is installed and accessible."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Extract version
                version_line = result.stdout.split('\n')[0]
                print(f"✓ FFmpeg found: {version_line}")
                return True
        except FileNotFoundError:
            print("✗ FFmpeg not found in PATH")
            return False
        except Exception as e:
            print(f"✗ Error checking FFmpeg: {e}")
            return False
        
        return False
    
    def check_video_file(self) -> bool:
        """Verify video file exists and is readable."""
        if not self.video_file.exists():
            print(f"✗ Video file not found: {self.video_file}")
            return False
        
        if not self.video_file.is_file():
            print(f"✗ Path is not a file: {self.video_file}")
            return False
        
        file_size_mb = self.video_file.stat().st_size / (1024 * 1024)
        print(f"✓ Video file found: {self.video_file.name} ({file_size_mb:.2f} MB)")
        
        # Try to get video info
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 
                 'format=duration,bit_rate', '-show_entries', 
                 'stream=width,height,r_frame_rate,codec_name',
                 '-of', 'default=noprint_wrappers=1', str(self.video_file)],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                info = result.stdout
                print(f"✓ Video info:")
                for line in info.strip().split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if key in ['width', 'height', 'r_frame_rate', 'codec_name', 'duration']:
                            print(f"  - {key}: {value}")
        except Exception as e:
            print(f"⚠ Could not read video info: {e}")
        
        return True
    
    def build_ffmpeg_command(self) -> list:
        """Build FFmpeg command for RTSP streaming to MediaMTX server."""
        cmd = [
            'ffmpeg',
            '-re',  # Read input at native frame rate (real-time)
            '-stream_loop', '-1',  # Infinite loop
            '-i', str(self.video_file),  # Input file
        ]
        
        # Optional: Change resolution
        if self.resolution:
            cmd.extend(['-s', self.resolution])
        
        # Optional: Change FPS
        if self.fps:
            cmd.extend(['-r', str(self.fps)])
        
        # Video codec settings (H.264 for best compatibility)
        cmd.extend([
            '-c:v', 'libx264',  # H.264 video codec
            '-preset', 'ultrafast',  # Encoding speed (ultrafast for low latency)
            '-tune', 'zerolatency',  # Tune for low latency
            '-g', '50',  # GOP size (keyframe interval)
            '-b:v', '2000k',  # Video bitrate
            '-maxrate', '2000k',
            '-bufsize', '4000k',
            '-pix_fmt', 'yuv420p',  # Pixel format for compatibility
        ])
        
        # Audio codec settings
        cmd.extend([
            '-c:a', 'aac',  # AAC audio codec
            '-b:a', '128k',  # Audio bitrate
        ])
        
        # RTSP output - stream TO MediaMTX server
        cmd.extend([
            '-f', 'rtsp',  # Output format
            '-rtsp_transport', 'tcp',  # Use TCP (more reliable than UDP)
            self.rtsp_url
        ])
        
        return cmd
    
    def start(self) -> bool:
        """Start RTSP streaming."""
        # Preflight checks
        print("="*60)
        print("RTSP Camera Simulator v1.0")
        print("="*60)
        print("\n[1/3] Checking FFmpeg...")
        
        if not self.check_ffmpeg():
            print("\n✗ FATAL: FFmpeg not installed")
            print("\nInstallation instructions:")
            print("  Windows: choco install ffmpeg")
            print("           OR download from https://ffmpeg.org/download.html")
            print("  Linux:   sudo apt install ffmpeg")
            print("  macOS:   brew install ffmpeg")
            return False
        
        print("\n[2/3] Checking video file...")
        if not self.check_video_file():
            print(f"\n✗ FATAL: Video file check failed")
            return False
        
        print("\n[3/3] Starting RTSP stream...")
        print(f"  RTSP URL: {self.rtsp_url}")
        print(f"  Port: {self.rtsp_port}")
        print(f"  Stream: {self.stream_name}")
        
        # Build command
        cmd = self.build_ffmpeg_command()
        
        # Show command (for debugging)
        print(f"\nFFmpeg command:")
        print(f"  {' '.join(cmd)}")
        
        try:
            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait a moment to check if it starts successfully
            time.sleep(2)
            
            if self.process.poll() is not None:
                # Process exited
                stderr = self.process.stderr.read() if self.process.stderr else ""
                print(f"\n✗ FFmpeg exited unexpectedly")
                print(f"Error output:\n{stderr}")
                return False
            
            print(f"\n✓ RTSP stream started successfully!")
            print(f"\n{'='*60}")
            print(f"Stream URL: {self.rtsp_url}")
            print(f"{'='*60}")
            print("\nUsage in EmberEye:")
            print(f"  1. Go to Camera Settings")
            print(f"  2. Add new camera")
            print(f"  3. Set URL: {self.rtsp_url}")
            print(f"  4. Click Connect")
            print("\nUsage with VLC Player:")
            print(f"  vlc {self.rtsp_url}")
            print("\nUsage with ffplay:")
            print(f"  ffplay {self.rtsp_url}")
            print(f"\n{'='*60}")
            print("Press Ctrl+C to stop streaming...")
            print(f"{'='*60}\n")
            
            # Monitor process
            return self.monitor()
            
        except Exception as e:
            print(f"\n✗ Error starting FFmpeg: {e}")
            return False
    
    def monitor(self) -> bool:
        """Monitor FFmpeg process and handle output."""
        try:
            # Read stderr in real-time (FFmpeg outputs to stderr)
            for line in iter(self.process.stderr.readline, ''):
                if not line:
                    break
                
                # Show important lines (frame info, errors)
                line = line.strip()
                if line.startswith('frame=') or 'error' in line.lower() or 'warning' in line.lower():
                    print(f"[FFmpeg] {line}")
            
            # Wait for process to complete
            self.process.wait()
            
            if self.process.returncode == 0:
                print("\n✓ Stream ended normally")
                return True
            else:
                print(f"\n✗ Stream ended with error (code {self.process.returncode})")
                return False
                
        except KeyboardInterrupt:
            print("\n\n⏸ Stopping stream...")
            self.stop()
            return True
        except Exception as e:
            print(f"\n✗ Error monitoring stream: {e}")
            return False
    
    def stop(self):
        """Stop RTSP streaming."""
        if self.process and self.process.poll() is None:
            print("Terminating FFmpeg process...")
            self.process.terminate()
            
            try:
                self.process.wait(timeout=5)
                print("✓ Stream stopped")
            except subprocess.TimeoutExpired:
                print("Force killing FFmpeg process...")
                self.process.kill()
                self.process.wait()
                print("✓ Stream force stopped")


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description='RTSP Camera Simulator - Stream video files via RTSP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stream with defaults (port 8554, stream name 'camera1')
  python rtsp_camera_simulator.py --video ../data/IMG_1318.MOV
  
  # Custom port and stream name
  python rtsp_camera_simulator.py --video video.mp4 --port 8555 --name camera2
  
  # Change resolution and FPS
  python rtsp_camera_simulator.py --video video.avi --resolution 1280x720 --fps 30
  
  # Multiple simulators (different ports)
  python rtsp_camera_simulator.py --video cam1.mov --port 8554 --name camera1 &
  python rtsp_camera_simulator.py --video cam2.mp4 --port 8555 --name camera2 &

Connect in EmberEye:
  RTSP URL: rtsp://localhost:8554/camera1
  
Test with VLC:
  vlc rtsp://localhost:8554/camera1
  
Test with ffplay:
  ffplay rtsp://localhost:8554/camera1
        """
    )
    
    parser.add_argument('--video', '-v', required=True,
                       help='Video file to stream (MOV, MP4, AVI, MKV, etc.)')
    parser.add_argument('--port', '-p', type=int, default=8554,
                       help='RTSP port (default: 8554)')
    parser.add_argument('--name', '-n', default='camera1',
                       help='Stream name (default: camera1)')
    parser.add_argument('--fps', type=int,
                       help='Override FPS (e.g., 30)')
    parser.add_argument('--resolution', '-r',
                       help='Override resolution (e.g., 1920x1080, 1280x720)')
    
    args = parser.parse_args()
    
    # Create simulator
    simulator = RTSPCameraSimulator(
        video_file=args.video,
        rtsp_port=args.port,
        stream_name=args.name,
        fps=args.fps,
        resolution=args.resolution
    )
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\nReceived interrupt signal...")
        simulator.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start streaming
    success = simulator.start()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
