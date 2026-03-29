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
- Done: 16
- In Progress: 3
- Not Started: 3
- Weighted completion: 79.5%

### Done

- Package structure and pyproject baseline for embereye_base
- AnalyticPlugin abstract contract
- Shared analytics data structures (FrameData, SensorReading, AnalyticResult)
- Hardware ID module with OS-specific retrieval paths
- License generation/signing CLI (embereye-license-sign)
- License schema fields implemented (customer, hardware_id, max_devices, analytics, expiry, signature)
- LicenseManager core flow (scan, merge, signature checks, invalid handling)
- LicenseManager API surface in roadmap week 3
- License folder watcher support and `licenses_changed` signal
- Field `LICENSES` tab with table view and add/remove license flows
- Device count status indicator in licensing UI
- Developer-facing license workflow and enforcement guide
- Focused unit test suites for hardware, payload, manager, signing helpers

### In Progress

- Move shared utilities from Field/Studio into Base (partially done for licensing + plugin contracts)
- Unit tests target in roadmap includes full UI interaction paths; backend/signal coverage is now in place
- Public key handling is implemented via runtime key path; packaging/embed policy still needs finalization

### Not Started

- Formal coverage report proving >= 80% target across embereye_base/license manager
- Device-limit exceedance alert dialog path based on live runtime count breach
- Tag embereye-suite/v2.0.0-dev.2

## Phase 2: Marketplace and Plugin System

Roadmap source: docs/v2.0/ROADMAP_EmberEye_Suite_2.0.md (Phase 2 section)

### Count Summary

- Total checklist items: 33
- Done: 28
- In Progress: 0
- Not Started: 5
- Weighted completion: 84.8%

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
- Formal `.eapkg` format specification in `docs/eapkg_format.md`
- Banner card precedence policy implementation (`License > Manual > Auto`)
- Multi-analytics slot conflict merge rules (severity/priority deterministic selection)
- Overflow summary indicator (`+N active analytics`) in fire and PPE banner overlays
- Field policy examples documented for multi-analytics scenarios
- Studio export-as-eapkg minimal path with validator compatibility checks
- Critical-card pin/non-evict behavior for constrained banner layouts
- Mode-switch persistence and runtime-reload E2E coverage for banner preferences
- Card widget parity: enable toggle, Configure action, Remove action, and license-gated behavior
- Import dialog UX parity: richer progress reporting and completion state details

### In Progress

- None currently.

### Not Started

- Full end-to-end tests for banner mode switching across sessions/restarts (comprehensive UI-runtime pass)
- Studio export metadata prompt/authoring UX refinements for operator flows
- Tag embereye-suite/v2.0.0-dev.3
- Final phase acceptance pass with roadmap checklist sign-off

## Combined Status (Phase 1 + Phase 2)

- Combined total items: 55
- Combined done: 44
- Combined in progress: 3
- Combined weighted completion: 82.7%

## Next Milestone to Lift Both Phases Fast

1. Close remaining Phase 1 release criteria:
   - coverage report proof + device-limit breach alert path
2. Finish Phase 2 final runtime gaps:
   - comprehensive mode-switch/session-restart validation + final acceptance pass
3. Expand Studio export with richer operator metadata prompts and stricter schema docs alignment
4. Run final checklist audit and cut `dev.2` / `dev.3` milestone tags
