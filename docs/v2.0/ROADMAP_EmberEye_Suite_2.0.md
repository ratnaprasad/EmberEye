# EmberEye Suite 2.0 – Development Roadmap

**Version:** 1.0  
**Date:** 20 March 2026  
**Branch:** `develop/2.x`  
**Base Tag:** `embereye-suite/v2.0.0-dev.0`  

> This is a solo-developer, effort-relative roadmap. Week estimates are working-week effort units, not calendar weeks. Adjust as needed based on actual progress.

---

## Summary

| Phase | Name | Effort | Deliverable |
|-------|------|--------|-------------|
| 0 | PyQt6 Migration & Base Environment | 2 weeks | PyQt6/Python 3.11 baseline |
| 1 | Core Library & Licensing | 6 weeks | EmberEye-Base package, license manager, UI |
| 2 | Marketplace & Plugin System | 6 weeks | Plugin manager, card UI, import flow |
| 3 | Analytics Execution Engine | 8 weeks | DAG scheduler, NodeGraphQt editor, JSON fallback |
| 4 | Testing & Automation | 6 weeks | CI pipeline, load test results, test reports |
| 5 | Polish & Release | 4 weeks | Installers, user manual, release notes |
| **Total** | | **~32 weeks** | **EmberEye Suite v2.0.0** |

---

## Phase 0: PyQt6 Migration & Base Environment
**Effort:** 2 weeks  
**Goal:** Upgrade the existing 1.x codebase to Python 3.11 and PyQt6, ensuring no regressions.

### Background
The current codebase uses PyQt5 (5.15.11) with 316 import lines and 123 `exec_()` call sites. PyQt6 6.10.2 and PyQt6-WebEngine 6.10.0 are available for Python 3.11. See [PyQt5→PyQt6 Migration Notes](#appendix-a-pyqt5--pyqt6-migration-notes) for the full change inventory.

### Tasks
- [ ] Create branch `feature/pyqt6-migration` from `develop/2.x`.
- [ ] Run automated pass: replace all `from PyQt5` → `from PyQt6` and `exec_()` → `exec()` via `sed`.
- [ ] Update Qt enum access to fully-qualified form (e.g., `Qt.AlignCenter` → `Qt.AlignmentFlag.AlignCenter`) — this is the most labour-intensive step.
- [ ] Fix `event.pos()` → `event.position().toPoint()` at 6 call sites in `embereye-field`.
- [ ] Replace `matplotlib.use('Qt5Agg')` → `matplotlib.use('QtAgg')` and `backend_qt5agg` → `backend_qtagg` in 4 source files.
- [ ] Move `QAction` imports from `QtWidgets` → `QtGui` in affected files.
- [ ] Update `requirements.txt`: remove `PyQt5`, `PyQtWebEngine`; add `PyQt6`, `PyQt6-WebEngine`.
- [ ] Update `build_windows.py` and `EmberEye_win.spec` / `embereye-studio.spec` for PyQt6.
- [ ] Verify application starts on Windows, Linux, and macOS with PyQt6.
- [ ] Run existing smoke tests and fix failures.
- [ ] Merge into `develop/2.x` and tag `embereye-suite/v2.0.0-dev.1`.

**Deliverables:** Working PyQt6/Python 3.11 baseline with no functional changes.

---

## Phase 1: Core Library & Licensing
**Effort:** 6 weeks  
**Goal:** Extract EmberEye-Base as a standalone package, implement RSA file-based licensing with merging, and provide the licensing UI in Field.

### Week 1 – EmberEye-Base Package
- [ ] Create Python package structure: `embereye_base/` with `__init__.py`, `pyproject.toml`.
- [ ] Move shared utilities (logging, hardware ID, plugin interfaces) from Field/Studio into Base.
- [ ] Define abstract base classes: `AnalyticPlugin` with `process_frame()`, `configure()`, `get_metadata()`.
- [ ] Define shared data structures: `FrameData`, `SensorReading`, `AnalyticResult`.
- [ ] Write unit tests targeting ≥ 80% coverage for Base module.

### Week 2 – Hardware ID & License Generation
- [ ] Implement `hardware_id.py` with platform-specific retrieval (MAC address, motherboard serial):
  - Windows: `wmic`, registry
  - Linux: `/sys/class/dmi/id/`
  - macOS: `ioreg`
- [ ] Build CLI tool `generate_license.py` (server-side):
  - Input: customer name, hardware ID, max devices, analytics list, optional expiry.
  - Output: signed `.lic` JSON file (RSA-2048 via `cryptography` library).
  - Private key never leaves build server.
- [ ] Embed RSA public key in the application package.
- [ ] Define license JSON schema with fields: `customer`, `hardware_id`, `max_devices`, `analytics`, `expiry`, `signature`.

### Week 3 – License Manager
- [ ] Implement `LicenseManager` class:
  - Scans configured license folder for `.lic` files on startup.
  - Verifies RSA signature of each file; rejects invalid files and logs errors.
  - Merges all valid licenses: `max_devices = max(all)`, `analytics = union(all)`.
- [ ] Provide API:
  - `is_analytic_licensed(analytic_id: str) -> bool`
  - `get_max_devices() -> int`
  - `get_current_device_count() -> int`
  - `get_license_summary() -> list[LicenseSummary]`
- [ ] Add `QFileSystemWatcher` on license folder to hot-reload on changes.
- [ ] Emit `licenses_changed` signal on reload.

### Week 4 – Licensing UI
- [ ] Add "Licenses" tab to Field's main window.
- [ ] Table widget with columns: Customer, Max Devices, Licensed Analytics, Expiry, Status.
- [ ] Show current device count vs. `max_devices` with colour indicator (green/amber/red).
- [ ] "Add License" button → `QFileDialog` (`.lic` filter) → copy to license folder → triggers hot-reload.
- [ ] Alert dialog if device count exceeds `max_devices` at any point.

### Weeks 5–6 – Unit Tests & Documentation
- [ ] Write unit tests: license merging, signature validation, expired/invalid file handling, UI signals.
- [ ] Achieve ≥ 80% coverage on `embereye_base` and `LicenseManager`.
- [ ] Update developer documentation with license workflow and key management procedures.
- [ ] Tag `embereye-suite/v2.0.0-dev.2`.

**Deliverables:** EmberEye-Base package, license manager, licensing UI, passing unit tests.

---

## Phase 2: Marketplace & Plugin System
**Effort:** 6 weeks  
**Goal:** Enable dynamic loading of analytics from `.eapkg` packages, with USB import and card-based UI.

### Week 1 – `.eapkg` Format Specification
- [ ] Specify `.eapkg` as a ZIP archive with the following mandatory structure:
  ```
  <name>-<version>.eapkg
  ├── metadata.json       # name, version, description, dependencies, execution_hints, required_license
  ├── <module_name>/      # Python analytic implementation
  │   ├── __init__.py
  │   └── analytic.py     # implements AnalyticPlugin
  └── assets/             # optional: model files, config
  ```
- [ ] Write `eapkg_validator.py` (standalone tool) to validate structure and metadata.
- [ ] Create a sample `.eapkg` package for testing.
- [ ] Document the schema in `docs/eapkg_format.md`.

### Weeks 2–3 – Plugin Manager
- [ ] Implement `PluginManager` class:
  - Monitors configurable folder (default `~/EmberEye/Marketplace`) via `QFileSystemWatcher`.
  - On new `.eapkg` detected: validate structure → load metadata → register in `PluginRegistry`.
  - Log and ignore invalid packages; do not crash.
- [ ] `PluginRegistry`: stores `AnalyticDescriptor` (metadata + load status + license status).
- [ ] Signals: `analytic_added(id)`, `analytic_removed(id)`, `analytic_updated(id)`.
- [ ] Dynamic import of analytic Python module using `importlib`.
- [ ] Isolate import errors: if module import fails, mark as `load_error`, continue.

### Week 4 – Analytics Card UI
- [ ] Create `AnalyticsCardWidget` (card component): name, version, license badge, enable/disable toggle.
- [ ] Create `AnalyticsCardsView` (grid layout): receives signals from `PluginManager`, adds/removes cards dynamically.
- [ ] Toggle is enabled only if `LicenseManager.is_analytic_licensed(id)` returns `True`.
- [ ] Context menu per card: **Configure**, **Remove**.
- [ ] "Remove" action deletes `.eapkg` from Marketplace folder; `PluginManager` handles the rest.

### Week 5 – Import from USB/Local
- [ ] Add "Import Analytics" button to Field toolbar.
- [ ] `ImportAnalyticsDialog`:
  - `QFileDialog.getExistingDirectory()` to select source folder.
  - Recursively scans for `*.eapkg` files.
  - Validates each file; shows progress bar (`QProgressDialog`).
  - Copies valid packages to Marketplace folder.
  - Summary screen: N imported, M failed (with error details per package).

### Week 6 – Integration & Testing
- [ ] Integration tests for the full import-load-display cycle.
- [ ] Error handling tests: corrupt ZIP, missing `metadata.json`, invalid module, duplicate ID.
- [ ] `pytest-qt` tests for card enable/disable toggling and import dialog flow.
- [ ] Tag `embereye-suite/v2.0.0-dev.3`.

**Deliverables:** Plugin manager, card UI, import functionality, integration tests.

---

## Phase 3: Analytics Execution Engine
**Effort:** 8 weeks  
**Goal:** Implement DAG-based execution, scheduling, and visual dependency editor (NodeGraphQt) with JSON fallback.

### Weeks 1–2 – Graph Model & Scheduler Core
- [ ] Implement `WorkflowGraph` class:
  - Backed by `networkx.DiGraph`.
  - Load from / save to `workflow.json`.
  - Cycle detection: `networkx.is_directed_acyclic_graph()`.
  - Topological sort: `networkx.topological_sort()`.
- [ ] Define `workflow.json` schema:
  ```json
  {
    "nodes": [{"id": "...", "analytic_id": "...", "trigger": {...}, "policy": "sequential|parallel"}],
    "edges": [{"source": "...", "target": "..."}]
  }
  ```
- [ ] Write unit tests for graph loading, cycle detection, topological sort.

### Weeks 3–4 – Scheduler with Triggers
- [ ] `AnalyticsScheduler` class:
  - Runs on `QTimer` (configurable tick rate).
  - Frame counter incremented per acquired frame.
  - Per-analytics trigger evaluation: `every_n_frames` (frame counter mod N == 0) or `every_seconds` (elapsed time ≥ T).
- [ ] Execution queue: enqueue analytics whose dependencies are satisfied AND trigger condition is met.
- [ ] Sequential policy: drain queue in topological order, one at a time.
- [ ] Parallel policy: `concurrent.futures.ThreadPoolExecutor`; independent nodes run concurrently.
- [ ] Thread-safe shared execution context (`threading.Lock` or Qt `QMutex`).
- [ ] Log per-analytic: start time, end time, duration, error (if any).

### Week 5 – Data Passing
- [ ] Define `ExecutionContext`: thread-safe dictionary keyed by analytic ID storing `AnalyticResult`.
- [ ] Upstream analytics write results to context; downstream analytics read from context by declaring dependencies.
- [ ] Context is cleared and rebuilt each scheduler cycle.
- [ ] Ensure no data race: writes complete before downstream reads begin (dependency order guarantees this in sequential mode; barriers/futures for parallel mode).

### Weeks 6–7 – NodeGraphQt Integration
- [ ] Verify NodeGraphQt compatibility with PyQt6; apply patches if needed.
- [ ] Create custom node class `AnalyticNode` with:
  - Input port: `data_in` (accepts upstream `AnalyticResult`).
  - Output port: `data_out` (produces `AnalyticResult`).
  - Node label: analytic name + version.
- [ ] Embed NodeGraphQt canvas in "Workflow" tab.
- [ ] Analytics palette (left panel): lists all registered analytics; drag to canvas to create a node.
- [ ] Node properties panel (right panel): trigger type, trigger value, execution policy.
- [ ] "Save Workflow" button: serialise canvas to `workflow.json` via `WorkflowGraph`.
- [ ] On tab open: if `workflow.json` exists, load and render graph.

### Week 8 – JSON Fallback
- [ ] On Field start, attempt to load `workflow.json`.
- [ ] If missing: start with empty workflow (no analytics scheduled); show info notification.
- [ ] If invalid JSON or schema error: show error dialog, fall back to last valid backup (`workflow.json.bak`).
- [ ] Maintain `workflow.json.bak` as the last known-good copy on every successful save.
- [ ] `WorkflowGraph.validate()` method that returns human-readable error descriptions.
- [ ] Tag `embereye-suite/v2.0.0-dev.4`.

**Deliverables:** Fully functional execution engine, visual dependency editor, unit tests for scheduler and graph.

---

## Phase 4: Testing & Automation
**Effort:** 6 weeks  
**Goal:** Achieve high test coverage, run load tests, and set up CI for cross-platform validation.

### Weeks 1–2 – Unit & Integration Test Expansion
- [ ] Expand unit tests to achieve ≥ 80% coverage across all new modules.
- [ ] Integration tests:
  - License merging with 3+ license files (including expired, invalid signature, duplicate analytics).
  - Full import-load-enable cycle for a `.eapkg` package.
  - DAG execution with a 3-node mock analytics chain (fire → overlay → alert).
- [ ] `pytest-qt` tests:
  - Card enable/disable toggling respects license state.
  - Import dialog shows correct progress and summary.
  - Licenses tab updates after adding a file.
  - Workflow editor saves and reloads correctly.

### Weeks 3–4 – Load Testing
- [ ] Build mock analytics factory: configurable CPU load and sleep duration per analytic.
- [ ] Load test scenarios using existing PFDS and RTSP simulators:
  - 20 analytics, 30 fps — measure CPU, memory, frame drops.
  - 50 analytics, 15 fps — stress test.
  - 10 analytics, 60 fps — high frame rate scenario.
- [ ] Reference hardware specification: document test machine specs (CPU, RAM, GPU, OS).
- [ ] Record and commit load test results to `docs/load_test_results.md`.
- [ ] Verify N1.1–N1.4 requirements are met.

### Week 5 – Automated UI Tests
- [ ] `pytest-qt` end-to-end journeys:
  1. Import analytic package from a local folder.
  2. Add a license file and verify the analytic becomes enabled.
  3. Drag two nodes to workflow, connect them, save, and reload.
  4. Start execution and verify analytics are triggered (mock analytics log timestamps).
- [ ] Run journeys on Windows (GitHub Actions), Linux (GitHub Actions), macOS (self-hosted or macOS runner).

### Week 6 – CI Setup & Reporting
- [ ] Configure GitHub Actions workflow for `develop/2.x`:
  - Matrix: `[windows-latest, ubuntu-latest, macos-latest]` × `python: ['3.11']`.
  - Steps: install deps → lint (flake8) → unit tests → integration tests → coverage report.
- [ ] Enforce minimum 80% coverage via `pytest-cov --fail-under=80`.
- [ ] Upload coverage reports to artifacts (or Codecov if desired).
- [ ] Load test script as manual-trigger workflow (`workflow_dispatch`).
- [ ] Tag `embereye-suite/v2.0.0-dev.5`.

**Deliverables:** CI pipeline, load test results, test reports.

---

## Phase 5: Polish & Release
**Effort:** 4 weeks  
**Goal:** Finalize documentation, packaging, and performance tuning.

### Week 1 – Performance Profiling
- [ ] Profile scheduler hot path with `cProfile`; identify top 5 bottlenecks.
- [ ] Use `py-spy` for wall-clock profiling under realistic load.
- [ ] Optimise: reduce lock contention, improve thread pool sizing, cache license lookups.
- [ ] Verify scheduler overhead ≤ 2 ms per frame (N1.2).
- [ ] Verify RSA license validation ≤ 100 ms per file (N1.4).

### Week 2 – User Documentation
- [ ] User Guide covering:
  - First-run setup and license installation.
  - Creating an analytic in Studio and exporting as `.eapkg`.
  - Importing an analytic into Field.
  - Configuring a workflow with dependencies.
  - Managing licenses (add, view, remove).
  - Troubleshooting: invalid packages, license errors, workflow JSON issues.
- [ ] Store in `docs/user_guide/`.
- [ ] Update `README.md` with 2.0 quick-start instructions.

### Week 3 – Packaging
- [ ] Update `EmberEye_win.spec` / `embereye-studio.spec` for PyQt6 + new modules.
- [ ] Build and test Windows installer (MSI via WiX or NSIS).
- [ ] Build and test Linux package (`.deb` or AppImage via PyInstaller).
- [ ] Build and test macOS `.dmg` (via PyInstaller + `create-dmg`).
- [ ] Validate installers on clean VMs (no Python pre-installed).
- [ ] Verify all assets (icons, resources) are bundled correctly.

### Week 4 – Release Candidate & Final Testing
- [ ] Tag `embereye-suite/v2.0.0-rc.1`.
- [ ] Full regression test run on all three platforms.
- [ ] Fix any critical issues found during RC testing.
- [ ] Write release notes (`CHANGELOG.md` entry for 2.0.0).
- [ ] Tag `embereye-suite/v2.0.0` (and component tags: `embereye-base/v2.0.0`, `embereye-field/v2.0.0`, `embereye-studio/v2.0.0`).
- [ ] Push release artifacts.

**Deliverables:** Installers, user manual, release notes, final `v2.0.0` tags.

---

## Tag Milestones

| Git Tag | Phase Completion |
|---------|-----------------|
| `embereye-suite/v2.0.0-dev.0` | Baseline (current HEAD) |
| `embereye-suite/v2.0.0-dev.1` | Phase 0 complete (PyQt6 baseline) |
| `embereye-suite/v2.0.0-dev.2` | Phase 1 complete (Core Library & Licensing) |
| `embereye-suite/v2.0.0-dev.3` | Phase 2 complete (Marketplace & Plugin System) |
| `embereye-suite/v2.0.0-dev.4` | Phase 3 complete (Execution Engine) |
| `embereye-suite/v2.0.0-dev.5` | Phase 4 complete (Testing & CI) |
| `embereye-suite/v2.0.0-rc.1` | Release candidate |
| `embereye-suite/v2.0.0` | Final release |

Component tags (`embereye-base/`, `embereye-field/`, `embereye-studio/`) mirror the suite tag at each milestone.

---

## Appendix A: PyQt5 → PyQt6 Migration Notes

> Reference for Phase 0 work. No files have been changed as of this date.

| Category | Severity | Count | Required Fix |
|----------|----------|-------|--------------|
| `from PyQt5` imports | HIGH | 316 lines | Mechanical `sed` replace → `from PyQt6` |
| `exec_()` calls | HIGH | 123 sites | Rename to `exec()` |
| Qt enum namespacing | HIGH | Many | `Qt.X` → `Qt.EnumClass.X` throughout |
| `event.pos()` (deprecated) | MEDIUM | 6 sites | `.position().toPoint()` |
| `Qt5Agg` / `backend_qt5agg` | MEDIUM | 4 files | → `QtAgg` / `backend_qtagg` |
| `QAction` import location | MEDIUM | ~2 files | `QtWidgets` → `QtGui` |
| `QWebEngineView` import prefix | LOW | 4 sites | `PyQt5` → `PyQt6` (already guarded) |
| High DPI `hasattr` guards | NONE | 22 sites | Already PyQt6-safe as written |
| `.ui` files / `loadUi` | NONE | 0 sites | Nothing to do |
| `requirements.txt` | LOW | 1 file | Replace `PyQt5`/`PyQtWebEngine` → `PyQt6`/`PyQt6-WebEngine` |

**Packages confirmed available for Python 3.11:**
- `PyQt6 == 6.10.2`
- `PyQt6-WebEngine == 6.10.0`

---

## Additional Notes

- **Phase 0 is a hard prerequisite.** All subsequent phases depend on the PyQt6 baseline. Allocate buffer time for third-party library compatibility issues (especially NodeGraphQt).
- **All three apps migrate together.** Mixing PyQt5 and PyQt6 in a single Python process is not supported; Base, Field, and Studio must all be migrated in Phase 0.
- **Keep a changelog.** Update `CHANGELOG.md` at each dev tag.
- **SRS is the requirements authority.** If requirements change during development, update `docs/SRS_EmberEye_Suite_2.0.md` first, then adjust this roadmap.

---

**End of Document**
