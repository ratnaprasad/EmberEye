# EmberEye Suite 2.0 - Phase 2 Implementation Plan

**Phase:** 2 - Marketplace & Plugin System  
**Date:** 27 March 2026  
**Branch:** `develop/2.x`

## Purpose

This document defines how Phase 2 work is organized across EmberEye-Base,
EmberEye-Field, and EmberEye-Studio, and the order in which implementation
 should proceed.

Phase 2 is focused on dynamic analytics packaging, import, discovery, loading,
and runtime presentation in Field.

Phase 1 is deferred for full implementation, but two minimal interfaces from
Phase 1 are required to unblock Phase 2:

- `AnalyticPlugin` base contract
- `LicenseManager` runtime interface for license state checks

## Architectural Split

### EmberEye-Base

EmberEye-Base owns the shared, non-UI runtime foundation for analytics
packaging and loading.

Responsibilities:

- Define the plugin contract all analytics must implement.
- Define analytic metadata and descriptor models.
- Validate `.eapkg` package structure and metadata.
- Watch the Marketplace folder and register/unregister analytics.
- Dynamically import analytic Python modules.
- Expose runtime license-check hooks used by Field.

Planned modules:

- `embereye_base/core/analytics/analytic_plugin.py`
- `embereye_base/core/marketplace/eapkg_validator.py`
- `embereye_base/core/marketplace/plugin_registry.py`
- `embereye_base/core/marketplace/plugin_manager.py`
- `embereye_base/core/licensing/license_manager.py`

### EmberEye-Field

EmberEye-Field owns the operator-facing runtime experience.

Responsibilities:

- Display imported analytics as cards.
- Allow import of `.eapkg` files from USB or local folders.
- Show license state and enable or disable analytic controls accordingly.
- Persist banner-card display mode and per-card visibility settings.
- Apply runtime display precedence for manual and automatic banner rendering.

Planned integration points:

- `embereye-field/fieldglass/main_window.py`
- `embereye-field/fieldglass/analytics_card_widget.py`
- `embereye-field/fieldglass/analytics_cards_view.py`
- `embereye-field/fieldglass/import_analytics_dialog.py`
- `embereye-field/util/fusionbanner.py`

### EmberEye-Studio

EmberEye-Studio owns analytic authoring and export.

Responsibilities:

- Export current analytic artifacts as `.eapkg`.
- Generate package metadata that matches the runtime validator contract.
- Bundle code, metadata, and optional assets into a valid package.

Planned integration points:

- Studio export service or packaging helper
- Studio menu or action: `Export as Analytics Package`

Studio is not the first implementation target for Phase 2. The package export
feature should be built only after Base defines the package contract and Field
can validate and consume it.

## Recommended Implementation Order

### Step 1 - Shared Base Contracts

Implement the minimum shared contracts first.

Scope:

- `AnalyticPlugin` abstract base class
- Shared metadata model for analytics descriptors
- `LicenseManager` interface or stub with `is_analytic_licensed()`

Reason:

Field card toggles and package loading depend on these contracts. Starting
with UI before these interfaces exist will create rework.

### Step 2 - `.eapkg` Format and Validation

Implement the package definition and validator.

Scope:

- `.eapkg` ZIP structure rules
- `metadata.json` schema checks
- validation result model
- sample package fixture for testing

Reason:

This stabilizes the external package contract before dynamic loading or Studio
export is built.

### Step 3 - Plugin Registry and Manager

Implement the runtime discovery and registration layer.

Scope:

- watched folder handling
- package scan on startup
- file-system change handling
- descriptor registration
- import error isolation
- add, remove, update signals

Reason:

This gives Field a reliable source of truth for analytics inventory.

### Step 4 - Field Marketplace UI

Implement the analytics cards and import workflow.

Scope:

- analytics cards view
- card widget with name, version, license state, enable toggle
- context menu actions
- import dialog with validation, copy, and summary reporting

Reason:

Once the runtime registry exists, the UI can bind directly to real plugin
events instead of temporary mocks.

### Step 5 - Banner Visibility Controls

Extend the existing Field fusion banner behavior.

Scope:

- `Auto` and `Manual` display mode selection
- per-card visibility persistence
- deterministic precedence rules
- license-aware visibility constraints
- overflow handling and multi-analytics display rules

Reason:

The repository already contains banner mode and manual card selection logic in
`fusionbanner.py`, so this should be evolved rather than replaced.

### Step 6 - Studio Export

Add Studio support for package generation.

Scope:

- export current analytic as `.eapkg`
- emit validator-compatible metadata
- bundle Python implementation and assets

Reason:

Studio export should target the already-stable package contract defined and
proven by Base and Field.

## Phase 2 Directory-Level Organization

### Base Layer

Primary home for shared runtime logic:

- `embereye_base/core/analytics/`
- `embereye_base/core/marketplace/`
- `embereye_base/core/licensing/`

This layer should contain no Field-specific widgets and no Studio-specific
export UI.

### Field Layer

Primary home for runtime UI and operator workflows:

- `embereye-field/fieldglass/`
- `embereye-field/util/`

This layer should consume Base services and avoid embedding package validation
or plugin loading rules directly in widgets.

### Studio Layer

Primary home for authoring-time export functionality:

- `embereye-studio/`

This layer should generate `.eapkg` output that conforms to Base validation
rules and should not own runtime plugin discovery logic.

## Immediate Coding Start

The first coding slice should be implemented in EmberEye-Base.

Initial deliverables:

1. `AnalyticPlugin` abstract base class
2. Minimal `LicenseManager` interface or stub
3. Package structure for `core/marketplace`
4. `.eapkg` validator skeleton
5. Descriptor and registry skeleton

This is the smallest useful slice that unlocks both Field runtime work and
later Studio export work.

## Non-Goals for the First Slice

The first coding slice should not include:

- full RSA licensing implementation
- full Studio export workflow
- final banner overflow policy implementation
- full scheduler or workflow engine work from Phase 3

## Decision Summary

Phase 2 starts in **EmberEye-Base**, then moves into **EmberEye-Field**, and
only then adds export support in **EmberEye-Studio**.

This order minimizes rework and ensures UI and export code are built against a
stable runtime contract.