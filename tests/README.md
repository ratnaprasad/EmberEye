# Tests

This folder contains integration, performance, and utility tests for EmberEye.

Run examples:

```bash
# Headless smoke test
python tests/smoke_test.py

# Full suite (pick individual scripts)
python tests/test_integration_e2e.py
python tests/test_performance.py
python tests/test_filtered_retrain.py
```

Load testing:

```bash
python tests/camera_stream_load_test.py --streams 4 --frames 500 --fps 30 --mode direct
python tests/tcp_sensor_load_test.py --streams 3 --duration 10 --fps 25
```
