# EmberEye Dashboard Tab Integration - Quick Reference

## Overview

The EmberEye application now includes a dedicated **📊 Metrics Dashboard** tab that embeds Grafana for real-time monitoring of system performance metrics.

## Tab Features

### Location
- **Main Window** → **Tab Bar** → **📊 Metrics Dashboard** (second tab after "Camera Feeds")

### Components

#### 1. URL Control Bar
- **Grafana URL Input:** Text field for entering Grafana dashboard URL
- **Load Dashboard Button:** Loads the specified URL in the embedded browser
- **↻ Refresh Button:** Reloads the current dashboard view

#### 2. Embedded Web View
- Full-featured web browser displaying Grafana dashboard
- Interactive: Click panels, zoom graphs, change time ranges
- Real-time updates (based on Grafana refresh interval)

## Usage

### First-Time Setup

1. **Install Grafana** (if not already installed):
   ```bash
   # macOS
   brew install grafana
   brew services start grafana
   
   # Or follow GRAFANA_SETUP.md for detailed instructions
   ```

2. **Configure Grafana**:
   - Access: http://localhost:3000
   - Login: admin/admin
   - Add Prometheus datasource: http://localhost:9090
   - Import EmberEye dashboard (see GRAFANA_SETUP.md)

3. **Launch EmberEye**:
   ```bash
   python main.py
   ```

4. **Access Dashboard Tab**:
   - Click **📊 Metrics Dashboard** tab
   - Default URL should already be configured
   - Click **Load Dashboard** if needed

### Default Configuration

The tab loads with a pre-configured Grafana URL from your `stream_config.json`:
```json
{
  "grafana_url": "http://localhost:3000"
}
```

### Recommended URLs

#### Standard Dashboard View
```
http://localhost:3000/d/emberye-metrics
```

#### Kiosk Mode (No Menus - Best for Embedded View)
```
http://localhost:3000/d/emberye-metrics?kiosk
```

#### Auto-Refresh with Time Range
```
http://localhost:3000/d/emberye-metrics?kiosk&refresh=5s&from=now-15m&to=now
```

#### TV Mode (Cycles Through Dashboards)
```
http://localhost:3000/d/emberye-metrics?kiosk&autofitpanels
```

## URL Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `kiosk` | Full-screen mode, hides menus | `?kiosk` |
| `refresh` | Auto-refresh interval | `?refresh=5s` |
| `from` | Start time | `?from=now-1h` |
| `to` | End time | `?to=now` |
| `theme` | Dashboard theme | `?theme=light` |
| `autofitpanels` | Auto-fit panels to view | `?autofitpanels` |

## Metrics Displayed

When properly configured, the dashboard shows:

### Camera Metrics (Per Stream)
- ✅ Frames processed per second
- ❌ Frame drop rate
- ⏱️ Vision detection latency (avg/p95)
- 📊 Current adaptive FPS
- 📈 Detection queue depth

### TCP Sensor Metrics
- 📦 Packets received per second
- ⚠️ Packet errors
- ⏱️ Processing latency
- 📊 Queue depth
- 🔌 Active connections

### Fusion Metrics
- 🚨 Alarm invocations per second
- ⏱️ Fusion latency
- 📊 Total alarms triggered

### System Metrics
- ⏰ Application uptime
- 💾 Memory usage (if configured)
- 🖥️ CPU usage (if configured)

## Troubleshooting

### Dashboard Not Loading

**Symptoms:** Blank page or error message

**Solutions:**
1. Verify Grafana is running:
   ```bash
   curl http://localhost:3000
   ```

2. Check URL format:
   - Must start with `http://` or `https://`
   - Example: `http://localhost:3000/d/emberye-metrics`

3. Try opening URL in external browser first

### No Data Displayed

**Symptoms:** Dashboard loads but panels show "No data"

**Solutions:**
1. Verify metrics endpoint is active:
   ```bash
   curl http://localhost:9090/metrics | grep emberye
   ```

2. Check Prometheus datasource in Grafana:
   - Configuration → Data Sources → EmberEye Prometheus
   - URL must be `http://localhost:9090`
   - Click "Save & Test"

3. Ensure EmberEye is running with streams active

### Connection Refused

**Symptoms:** "Connection refused" or "Can't reach this page"

**Solutions:**
1. Start Grafana:
   ```bash
   # macOS
   brew services start grafana
   
   # Linux
   sudo systemctl start grafana-server
   ```

2. Check Grafana port (default 3000):
   ```bash
   lsof -i :3000
   ```

3. Try default URL: `http://localhost:3000`

### PyQtWebEngine Not Available

**Symptoms:** Error message about missing QWebEngine

**Solution:**
```bash
pip install PyQtWebEngine
```

## Advanced Configuration

### Remote Grafana Server

To use Grafana on a different machine:

1. Update URL in EmberEye dashboard tab:
   ```
   http://192.168.1.100:3000/d/emberye-metrics?kiosk
   ```

2. Ensure Prometheus is accessible from Grafana server

3. Update Grafana datasource URL to point to EmberEye machine

### Custom Port

If Grafana runs on a different port:
```
http://localhost:8080/d/emberye-metrics
```

Update in:
- EmberEye dashboard tab URL field
- `stream_config.json` → `grafana_url`

### Authentication

For Grafana instances with authentication:
1. Create API key in Grafana
2. Use URL with auth token:
   ```
   http://localhost:3000/d/emberye-metrics?auth_token=YOUR_TOKEN
   ```

## Keyboard Shortcuts (in Dashboard Tab)

| Key | Action |
|-----|--------|
| `Ctrl/Cmd + R` | Refresh dashboard |
| `Ctrl/Cmd + F` | Search (if not in kiosk mode) |
| `F5` | Reload page |
| `Escape` | Exit fullscreen/kiosk mode |

## Performance Notes

### Resource Usage
- Embedded browser adds ~200-300MB RAM overhead
- Negligible CPU impact when dashboard is not active tab
- Real-time updates only when tab is visible

### Optimization
- Use `?kiosk` to reduce UI rendering overhead
- Set longer refresh intervals for lower CPU usage: `?refresh=10s`
- Limit time range to reduce query complexity: `?from=now-5m`

## Integration with Other Tabs

The metrics dashboard complements the **Camera Feeds** tab:
- **Camera Feeds:** Live video streams with thermal overlays and alarms
- **Metrics Dashboard:** Performance analytics and system health

Switch between tabs to:
1. Monitor live camera feeds
2. Analyze performance metrics
3. Identify bottlenecks or issues
4. Verify scaling improvements

## Next Steps

1. ✅ **Complete Grafana setup** → See `GRAFANA_SETUP.md`
2. 📊 **Import dashboard** → See dashboard JSON in `ADAPTIVE_FPS_METRICS_GUIDE.md`
3. 🔍 **Configure alerts** → Set up notifications for critical conditions
4. 📈 **Run load tests** → Monitor metrics under stress (see `LOAD_TEST_RESULTS.md`)

## Support

For detailed setup instructions, see:
- **GRAFANA_SETUP.md** - Complete Grafana installation and configuration
- **ADAPTIVE_FPS_METRICS_GUIDE.md** - Metrics documentation and PromQL queries
- **SCALING_ROADMAP.md** - Performance targets and monitoring guidelines
