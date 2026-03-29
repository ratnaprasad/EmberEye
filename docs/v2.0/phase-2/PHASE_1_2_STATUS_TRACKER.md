# EmberEye Suite 2.0 - Phase 1 and Phase 2 Status Tracker

Date: 2026-03-29  
Branch: chore/phase2-main-sync-recovery

Progress formula used in this tracker:

- weighted_progress = (done + 0.5 * in_progress) / total

This avoids over-reporting when a checklist item is only partially complete.

## Phase 1: Core Library and Licensing

Roadmap source: docs/v2.0/ROADMAP_EmberEye_Suite_2.0.md (Phase 1 section)

### Count Summary

- Total checklist items: 22
- Done: 10
- In Progress: 3
- Not Started: 9
- Weighted completion: 52.3%

### Done

- Package structure and pyproject baseline for embereye_base
- AnalyticPlugin abstract contract
- Shared analytics data structures (FrameData, SensorReading, AnalyticResult)
- Hardware ID module with OS-specific retrieval paths
- License generation/signing CLI (embereye-license-sign)
- License schema fields implemented (customer, hardware_id, max_devices, analytics, expiry, signature)
- LicenseManager core flow (scan, merge, signature checks, invalid handling)
- LicenseManager API surface in roadmap week 3
- Developer-facing license workflow and enforcement guide
- Focused unit test suites for hardware, payload, manager, signing helpers

### In Progress

- Move shared utilities from Field/Studio into Base (partially done for licensing + plugin contracts)
- Unit tests target in roadmap includes UI signals; backend tests are done but UI signal coverage is pending
- Public key handling is implemented via runtime key path, but explicit packaging/embed policy still needs finalization

### Not Started

- License folder QFileSystemWatcher hot-reload
- licenses_changed signal emission
- Full Licensing UI in Field (Licenses tab, table, add flow, limit alerts)
- Device count colour indicator in licensing UI
- Coverage target evidence for >= 80% (formal coverage report not produced yet)
- Tag embereye-suite/v2.0.0-dev.2

## Phase 2: Marketplace and Plugin System

Roadmap source: docs/v2.0/ROADMAP_EmberEye_Suite_2.0.md (Phase 2 section)

### Count Summary

- Total checklist items: 33
- Done: 15
- In Progress: 4
- Not Started: 14
- Weighted completion: 51.5%

### Done

- eapkg validator implementation
- Sample eapkg package fixture
- PluginManager implemented with discovery + validation + dynamic import + failure isolation
- PluginRegistry and descriptor storage
- Marketplace scan/update/remove behavior integrated
- Analytics cards UI base implementation in Field
- Import analytics flow in Field (scan, validate, copy, summary)
- Integration-style tests for import-load-display and plugin manager lifecycle
- Error handling coverage for package validation paths (corrupt/invalid package scenarios)

### In Progress

- Formal eapkg schema documentation file requested by roadmap (separate docs/eapkg_format.md pending)
- Card widget feature parity (Configure/Remove and full license-state wiring requires completion)
- Import dialog UX parity with roadmap details (progress dialog and full operator flow polish)
- pytest-qt card behavior coverage exists partially, but not complete for all roadmap scenarios

### Not Started

- Banner display mode selector Auto/Manual completion and persistence
- Per-card visibility persistence and runtime reload
- Display precedence rules implementation and tests
- Multi-analytics composition policy (priority, pinning, overflow, slot-merge rules)
- Overflow summary card (+N active analytics) behavior
- Field UI spec examples for multi-analytics rules
- Studio export-as-eapkg implementation and integration
- Tag embereye-suite/v2.0.0-dev.3

## Combined Status (Phase 1 + Phase 2)

- Combined total items: 55
- Combined done: 25
- Combined in progress: 7
- Combined weighted completion: 51.8%

## Next Milestone to Lift Both Phases Fast

1. Finish Phase 1 licensing runtime integration in Field:
   - watcher + signal + Licenses tab
2. Finish Phase 2 banner behavior block:
   - Auto/Manual + persistence + precedence tests
3. Add docs/eapkg_format.md and close schema-documentation gap
4. Add Studio export-as-eapkg minimal path
