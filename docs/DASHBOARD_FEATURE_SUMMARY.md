# EmberEye Dashboard Integration - Feature Summary

## 🎉 New Feature: Embedded Grafana Dashboard Tab

EmberEye now includes a dedicated metrics dashboard tab that provides real-time monitoring and analytics for system performance.

### What's New

#### 📊 Metrics Dashboard Tab
- **Location:** Main window → Tab bar (next to "Camera Feeds")
- **Feature:** Embedded Grafana web view for live metrics visualization
- **Benefits:** Monitor system performance without leaving the application

#### 🔧 Components Added

1. **main_window.py**
   - New `init_grafana_tab()` method
   - Embedded QWebEngineView for Grafana dashboard
   - URL configuration and control buttons
   - Automatic config persistence

2. **GRAFANA_SETUP.md**
   - Complete Grafana installation guide
   - Prometheus datasource configuration
   - Dashboard import instructions
   - Troubleshooting guide

3. **DASHBOARD_TAB_GUIDE.md**
   - Quick reference for using the dashboard tab
   - URL parameter guide
   - Keyboard shortcuts
   - Performance tips

4. **requirements.txt**
   - Added `PyQtWebEngine` dependency for web view support

### Quick Start

#### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 2. Install Grafana (Optional but Recommended)
```bash
# macOS
brew install grafana
brew services start grafana

# Access at: http://localhost:3000
# Default login: admin/admin
```

#### 3. Launch EmberEye
```bash
python main.py
```

#### 4. Access Dashboard Tab
- Click **📊 Metrics Dashboard** tab
- Enter Grafana URL (default: `http://localhost:3000`)
- Click **Load Dashboard**

### Features

#### Real-Time Monitoring
- ✅ Camera feed processing rates
- ❌ Frame drop statistics
- ⏱️ Vision detection latency (avg/P95)
- 📊 Adaptive FPS adjustments
- 📦 TCP sensor packet rates
- 🚨 Sensor fusion alarms
- 🔌 Active connections

#### Interactive Dashboard
- Zoom and pan on graphs
- Click-through to detailed metrics
- Adjust time ranges
- Refresh on demand
- Fullscreen/kiosk mode

#### Configuration Persistence
- Dashboard URL saved to `stream_config.json`
- Automatic restoration on app restart
- Per-deployment customization

### Usage Examples

#### Default Dashboard (With Menus)
```
http://localhost:3000/d/emberye-metrics
```

#### Kiosk Mode (Recommended for Embedded View)
```
http://localhost:3000/d/emberye-metrics?kiosk&refresh=5s
```

#### Production Monitoring (15-Minute Window)
```
http://localhost:3000/d/emberye-metrics?kiosk&refresh=5s&from=now-15m&to=now
```

### Integration with Existing Features

The dashboard tab works seamlessly with existing EmberEye capabilities:

#### Camera Feeds Tab
- View live video streams with thermal overlays
- See alarm indicators in real-time
- Maximize individual feeds

#### Metrics Dashboard Tab
- Analyze performance across all cameras
- Identify bottlenecks and issues
- Monitor system health metrics

#### TCP Sensor Integration
- Track sensor packet rates
- View connection status
- Analyze fusion algorithm performance

### Architecture

```
EmberEye Application
├── Camera Feeds Tab
│   ├── Live RTSP streams (VideoWidget)
│   ├── Thermal overlays
│   └── Alarm indicators
│
├── Metrics Dashboard Tab  ← NEW
│   ├── QWebEngineView (embedded browser)
│   ├── Grafana dashboard interface
│   └── Real-time metrics visualization
│
└── Backend Services
    ├── Metrics Server (port 9090)
    ├── Prometheus format exporter
    ├── TCP Sensor Server (port 9001)
    └── Video Workers (adaptive FPS)
```

### Metrics Exposed

The application exposes 16 Prometheus metrics:

#### Camera Metrics (Per Stream)
- `emberye_frames_processed_total{stream_id}`
- `emberye_frames_dropped_total{stream_id}`
- `emberye_vision_detection_latency_avg_ms{stream_id}`
- `emberye_vision_detection_latency_p95_ms{stream_id}`
- `emberye_vision_queue_depth{stream_id}`
- `emberye_camera_fps_current{stream_id}`

#### TCP Metrics
- `emberye_tcp_packets_received_total`
- `emberye_tcp_packet_errors_total`
- `emberye_tcp_packet_latency_avg_ms`
- `emberye_tcp_queue_depth`
- `emberye_tcp_connections_active`

#### Fusion Metrics
- `emberye_fusion_invocations_total`
- `emberye_fusion_alarms_total`
- `emberye_fusion_latency_avg_ms`

#### System Metrics
- `emberye_uptime_seconds`

### Configuration

#### Default Config (stream_config.json)
```json
{
  "groups": ["Default"],
  "streams": [...],
  "tcp_port": 9001,
  "metrics_port": 9090,
  "grafana_url": "http://localhost:3000",
  "tcp_mode": "async"
}
```

#### Customization Options
- **grafana_url:** Change Grafana server address
- **metrics_port:** Change Prometheus endpoint port
- **tcp_port:** Change sensor server port

### Testing

#### Verify Metrics Endpoint
```bash
curl http://localhost:9090/metrics | grep emberye
```

Expected output:
```
emberye_uptime_seconds 123.45
emberye_frames_processed_total{stream_id="cam_001"} 450
...
```

#### Verify Grafana Connection
```bash
curl http://localhost:3000/api/health
```

Expected output:
```json
{"database":"ok","version":"10.x.x"}
```

#### Test Dashboard Tab
1. Start EmberEye
2. Switch to 📊 Metrics Dashboard tab
3. Verify Grafana loads
4. Check panels show data

### Troubleshooting

#### Common Issues

**1. Dashboard Tab Shows Blank Page**
- Solution: Verify Grafana is running at configured URL
- Test: Open URL in external browser first

**2. No Metrics Data in Grafana**
- Solution: Verify Prometheus datasource configured correctly
- Test: Check http://localhost:9090/metrics shows data

**3. PyQtWebEngine Not Found**
- Solution: `pip install PyQtWebEngine`
- Note: Added to requirements.txt

**4. Connection Refused**
- Solution: Start Grafana service
- macOS: `brew services start grafana`
- Linux: `sudo systemctl start grafana-server`

### Documentation

Comprehensive guides available:

1. **GRAFANA_SETUP.md**
   - Complete Grafana installation
   - Datasource configuration
   - Dashboard import
   - Alert setup

2. **DASHBOARD_TAB_GUIDE.md**
   - Quick reference for dashboard tab
   - URL parameters guide
   - Keyboard shortcuts
   - Performance optimization

3. **ADAPTIVE_FPS_METRICS_GUIDE.md**
   - Full metrics documentation
   - PromQL query examples
   - Dashboard JSON templates
   - Alert rule examples

4. **SCALING_ROADMAP.md**
   - Performance targets
   - Monitoring guidelines
   - Capacity planning

### Benefits

#### For Operators
- 👁️ Real-time visibility into system performance
- 🎯 Quick identification of issues
- 📊 Historical trend analysis
- 🚨 Proactive monitoring with alerts

#### For Developers
- 🔍 Performance profiling
- 🐛 Debugging bottlenecks
- 📈 Scaling validation
- ✅ Load testing verification

#### For Management
- 📊 System health dashboards
- 💰 Capacity planning data
- 📉 Downtime analysis
- ✅ SLA compliance tracking

### Future Enhancements

Potential improvements for future releases:

1. **Multiple Dashboard Views**
   - Camera-specific dashboards
   - System health overview
   - Historical analysis view

2. **Alert Integration**
   - In-app alert notifications
   - Email/SMS forwarding
   - Escalation policies

3. **Custom Metrics**
   - User-defined KPIs
   - Business metrics
   - Custom thresholds

4. **Dashboard Templates**
   - Pre-built dashboard library
   - One-click import
   - Role-based views

### Related Features

This dashboard integration complements:
- ✅ Adaptive frame rate control
- ✅ Prometheus metrics exporter
- ✅ Async TCP sensor server
- ✅ Sensor fusion algorithm
- ✅ Thermal overlay visualization

### Getting Help

For detailed instructions and troubleshooting:
1. See `GRAFANA_SETUP.md` for installation
2. See `DASHBOARD_TAB_GUIDE.md` for usage
3. See `ADAPTIVE_FPS_METRICS_GUIDE.md` for metrics
4. Check application logs for errors

### Summary

The new Grafana dashboard tab provides:
- ✅ Real-time metrics visualization
- ✅ Embedded browser for seamless UX
- ✅ Configurable URLs and persistence
- ✅ Comprehensive monitoring capabilities
- ✅ Production-ready observability

**Result:** Complete monitoring solution integrated directly into EmberEye application.
