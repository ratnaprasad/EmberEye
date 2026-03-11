import os
import sys


# Ensure tests can import top-level project modules when pytest uses testpaths.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Legacy test compatibility: some tests import modules as top-level names.
EXTRA_IMPORT_PATHS = [
    os.path.join(PROJECT_ROOT, "embereye-field", "fieldglass"),
    os.path.join(PROJECT_ROOT, "embereye", "core"),
]
for path in EXTRA_IMPORT_PATHS:
    if path not in sys.path:
        sys.path.insert(0, path)
