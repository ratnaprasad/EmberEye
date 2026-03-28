# Grafana Dashboard Setup Guide

The EmberEye application now includes an embedded Grafana dashboard tab for real-time metrics monitoring. This guide will help you set up Grafana to visualize the Prometheus metrics.

## Quick Start

### 1. Install Grafana

**macOS (with Homebrew):**
```bash
brew install grafana
brew services start grafana
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install grafana
sudo systemctl start grafana-server
```

**Windows:**
Download installer from: https://grafana.com/grafana/download

### 2. Access Grafana

1. Open browser to http://localhost:3000
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin` (you'll be prompted to change it)

### 3. Configure Prometheus Data Source

1. Go to **Configuration** → **Data Sources** → **Add data source**
2. Select **Prometheus**
3. Configure:
   - **Name:** `EmberEye Prometheus`
   - **URL:** `http://localhost:9090`
   - **Scrape interval:** `15s` (or your configured interval)
4. Click **Save & Test** (should show green success message)

### 4. Import EmberEye Dashboard

#### Option A: Manual Import (Recommended)

1. Go to **Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select the dashboard JSON from `ADAPTIVE_FPS_METRICS_GUIDE.md` (see "Grafana Dashboard JSON" section)
4. Or create a new file `emberye-dashboard.json` with this content:

```json
{
  "dashboard": {
    "title": "EmberEye Monitoring",
    "tags": ["emberye", "fire-detection"],
    "timezone": "browser",
    "panels": [
      {
        "title": "System Overview",
        "type": "stat",
        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "emberye_uptime_seconds",
            "legendFormat": "Uptime (s)"
          }
        ]
      },
      {
        "title": "Camera Processing Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 4},
        "targets": [
          {
            "expr": "rate(emberye_frames_processed_total[1m])",
            "legendFormat": "{{stream_id}}"
          }
        ]
      },
      {
        "title": "Frame Drop Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 4},
        "targets": [
          {
            "expr": "rate(emberye_frames_dropped_total[1m])",
            "legendFormat": "{{stream_id}}"
          }
        ]
      },
      {
        "title": "Vision Detection Latency (Avg)",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
        "targets": [
          {
            "expr": "emberye_vision_detection_latency_avg_ms",
            "legendFormat": "{{stream_id}}"
          }
        ]
      },
      {
        "title": "Adaptive FPS by Stream",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
        "targets": [
          {
            "expr": "emberye_camera_fps_current",
            "legendFormat": "{{stream_id}}"
          }
        ]
      },
      {
        "title": "TCP Packet Rate",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 20},
        "targets": [
          {
            "expr": "rate(emberye_tcp_packets_received_total[1m])",
            "legendFormat": "Packets/sec"
          }
        ]
      },
      {
        "title": "TCP Queue Depth",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 20},
        "targets": [
          {
            "expr": "emberye_tcp_queue_depth",
            "legendFormat": "Queue Depth"
          }
        ]
      },
      {
        "title": "Sensor Fusion Alarms",
        "type": "graph",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 28},
        "targets": [
          {
            "expr": "rate(emberye_fusion_alarms_total[1m])",
            "legendFormat": "Alarms/sec"
          }
        ]
      }
    ],
    "refresh": "5s",
    "time": {"from": "now-15m", "to": "now"}
  }
}
```

5. Click **Import**

#### Option B: Use Embedded Dashboard

1. Start EmberEye application: `python main.py`
2. Switch to **📊 Metrics Dashboard** tab
3. Enter Grafana URL: `http://localhost:3000/d/emberye-metrics` (or your dashboard URL)
4. Click **Load Dashboard**

### 5. Verify Metrics Flow

1. **Check Prometheus is scraping:**
   - Open http://localhost:9090
   - Go to **Status** → **Targets**
   - Verify EmberEye metrics endpoint is UP

2. **Test metrics endpoint:**
   ```bash
   curl http://localhost:9090/metrics | grep emberye
   ```

3. **Verify Grafana displays data:**
   - Check that panels show live data
   - If no data, verify:
     - EmberEye application is running
     - Metrics server started (check console for "Metrics endpoint available at...")
     - Prometheus datasource configured correctly

## Dashboard Features

### Real-Time Monitoring
- **System Uptime:** Total application runtime
- **Camera Feeds:** Processing rate, FPS, latency per stream
- **Frame Drops:** Identify struggling cameras
- **Adaptive FPS:** See real-time FPS adjustments
- **TCP Sensors:** Packet rate, queue depth, error rate
- **Sensor Fusion:** Alarm frequency, latency

### Alerting (Optional)

Create alerts for critical conditions:

1. Go to **Alerting** → **Alert rules** → **New alert rule**
2. Example alert: **High Frame Drop Rate**
   - Query: `rate(emberye_frames_dropped_total[1m]) > 0.1`
   - Condition: Alert when value > threshold
   - Contact point: Email/Slack/etc.

## Using the Embedded Dashboard

### In-App Configuration

1. Launch EmberEye: `python main.py`
2. Navigate to **📊 Metrics Dashboard** tab
3. Configure Grafana URL in the input field
4. Click **Load Dashboard** to embed

### URL Formats

- **Dashboard view:** `http://localhost:3000/d/emberye-metrics`
- **Kiosk mode (fullscreen):** `http://localhost:3000/d/emberye-metrics?kiosk`
- **Specific time range:** `http://localhost:3000/d/emberye-metrics?from=now-1h&to=now`
- **Auto-refresh:** `http://localhost:3000/d/emberye-metrics?refresh=5s`

### Recommended Configuration

For embedded view in EmberEye:
```
http://localhost:3000/d/emberye-metrics?kiosk&refresh=5s&from=now-15m&to=now
```

## Troubleshooting

### Grafana not starting
- Check if port 3000 is available: `lsof -i :3000`
- View logs: 
  - macOS/Linux: `tail -f /usr/local/var/log/grafana/grafana.log`
  - Windows: Check Event Viewer

### No metrics in Grafana
1. Verify EmberEye metrics endpoint: `curl http://localhost:9090/metrics`
2. Check Prometheus targets: http://localhost:9090/targets
3. Verify datasource URL in Grafana (must be `http://localhost:9090`, NOT `9090`)

### Embedded view shows blank page
- Check browser console (F12) for CORS errors
- Try kiosk mode: add `?kiosk` to URL
- Verify Grafana is accessible in external browser first

### PyQtWebEngine not available
If you see "QWebEngine not available" error:
```bash
pip install PyQtWebEngine
```

## Advanced Configuration

### Custom Metrics Port

If using non-default metrics port, update Prometheus config:

**prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'emberye'
    static_configs:
      - targets: ['localhost:9091']  # Change from 9090 to your port
    scrape_interval: 15s
```

### Remote Grafana

To use a remote Grafana instance:
1. Update Grafana URL in EmberEye to remote address (e.g., `http://192.168.1.100:3000`)
2. Ensure Prometheus is accessible from Grafana server
3. Update Prometheus datasource URL in Grafana to EmberEye server IP

### Dashboard Customization

Edit panels in Grafana:
1. Click panel title → **Edit**
2. Modify queries, thresholds, colors
3. Save dashboard
4. Reload in EmberEye app

## Reference

- Full metrics documentation: `ADAPTIVE_FPS_METRICS_GUIDE.md`
- Grafana documentation: https://grafana.com/docs/
- Prometheus query guide: https://prometheus.io/docs/prometheus/latest/querying/basics/
