#!/usr/bin/env python3
import subprocess, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_MD = ROOT / 'TEST_COVERAGE_SUMMARY.md'

suites = [
  'test_embereye_suite_fixed.py',
  'test_auth_user_management.py',
  'test_ai_sensor_components.py',
  'test_ui_workflows.py'
]

print('Running coverage for test suites...')
# Clean previous data
if (ROOT / '.coverage').exists():
    os.remove(ROOT / '.coverage')

# Try pytest first; fall back to running files
try:
    subprocess.run(['coverage','run','-m','pytest'], cwd=ROOT, check=True)
except Exception:
    for f in suites:
        subprocess.run(['coverage','run','-a', f], cwd=ROOT, check=True)

# Generate XML and report (tolerate errors on missing source)
try:
    subprocess.run(['coverage','xml','-o','coverage.xml'], cwd=ROOT, check=True)
except Exception as e:
    print('coverage xml failed:', e)
rep = subprocess.run(['coverage','report','-m'], cwd=ROOT, capture_output=True, text=True)
print(rep.stdout)

# Parse total line from report output for summary
total_line = ''
for line in rep.stdout.splitlines():
    if line.strip().startswith('TOTAL'):
        total_line = line
        break

# Minimal markdown summary
content = f"""
# Test Coverage Summary

- Total: {total_line or 'See coverage.xml'}
- Generated: {os.popen('date').read().strip()}

To inspect details:
- Open `coverage.xml` in your IDE or use `coverage html` then open `htmlcov/index.html`.
"""
SUMMARY_MD.write_text(content)
print(f"Updated {SUMMARY_MD}")
