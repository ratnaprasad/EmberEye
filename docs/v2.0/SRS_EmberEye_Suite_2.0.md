# Software Requirements Specification (SRS)
## EmberEye Suite 2.0

**Version:** 1.0  
**Date:** 20 March 2026  
**Prepared for:** EmberEye Development Team  

---

## Table of Contents

1. [Introduction](#1-introduction)
   1. [Purpose](#11-purpose)
   2. [Scope](#12-scope)
   3. [Definitions, Acronyms, and Abbreviations](#13-definitions-acronyms-and-abbreviations)
   4. [References](#14-references)
   5. [Overview](#15-overview)

2. [Overall Description](#2-overall-description)
   1. [Product Perspective](#21-product-perspective)
   2. [Product Functions](#22-product-functions)
   3. [User Characteristics](#23-user-characteristics)
   4. [Constraints](#24-constraints)
   5. [Assumptions and Dependencies](#25-assumptions-and-dependencies)

3. [Specific Requirements](#3-specific-requirements)
   1. [External Interface Requirements](#31-external-interface-requirements)
      - [User Interfaces](#311-user-interfaces)
      - [Hardware Interfaces](#312-hardware-interfaces)
      - [Software Interfaces](#313-software-interfaces)
      - [Communication Interfaces](#314-communication-interfaces)
   2. [Functional Requirements](#32-functional-requirements)
      - [EmberEye-Base (Core Library)](#321-embereye-base-core-library)
      - [Licensing Module](#322-licensing-module)
      - [Marketplace & Plugin Management](#323-marketplace--plugin-management)
      - [Analytics Execution Engine](#324-analytics-execution-engine)
      - [User Interface (Field & Studio)](#325-user-interface-field--studio)
   3. [Non-Functional Requirements](#33-non-functional-requirements)
      - [Performance](#331-performance)
      - [Security](#332-security)
      - [Reliability](#333-reliability)
      - [Usability](#334-usability)
      - [Maintainability](#335-maintainability)
      - [Portability](#336-portability)

4. [Appendices](#4-appendices)
   1. [Glossary](#41-glossary)
   2. [Use Cases](#42-use-cases)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements for the EmberEye Suite 2.0 upgrade. The suite consists of three desktop applications (EmberEye-Base, EmberEye-Field, EmberEye-Studio) and an offline Marketplace component. The goal is to transform the existing tightly-coupled 1.x version into a modular, dynamically extensible platform with flexible analytics execution, node-locked licensing, and comprehensive testing.

### 1.2 Scope
The EmberEye Suite 2.0 will:
- Provide a core library (Base) shared across applications.
- Introduce a dynamic plugin system for analytics, allowing them to be authored in Studio, exported as packages, and imported into Field via a Marketplace UI.
- Implement a node-locked licensing system with per-device and per-analytics enforcement, supporting floating device upgrades via license file merging.
- Enable users to define analytics execution workflows (sequential/parallel, scheduled triggers) using a visual dependency editor, with a JSON fallback for manual configuration.
- Include a licensing management UI in Field to view and add licenses.
- Ensure cross-platform compatibility (Windows, Linux, macOS) with Python 3.11 and PyQt6.
- Deliver a complete testing suite covering unit, integration, load, and UI automation tests.

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| **Analytic** | A self-contained algorithm (e.g., fire detection, PPE detection) that processes sensor data. |
| **Base** | Core library shared across Field and Studio. |
| **DAG** | Directed Acyclic Graph – representation of analytics dependencies. |
| **EAPKG** | EmberEye Analytics Package – file format (ZIP) containing an analytic. |
| **Field** | Runtime environment that executes analytics. |
| **Marketplace** | Offline repository of analytics (folder) with a UI for importing from USB/local drives. |
| **NodeGraphQt** | Open-source library for visual node graph editing. |
| **PFDS** | Physical Fire Detection System – hardware with sensors (cameras, thermal, gas, etc.). |
| **Studio** | Authoring tool for building analytics (annotation, training, model export). |

### 1.4 References
- NodeGraphQt Documentation: https://nodegraphqt.readthedocs.io/
- PyQt6 Documentation: https://www.riverbankcomputing.com/static/Docs/PyQt6/
- Python 3.11 Documentation: https://docs.python.org/3.11/

### 1.5 Overview
Section 2 provides an overall description of the product and its environment. Section 3 details the functional and non-functional requirements. Section 4 contains supporting information including the glossary and detailed use cases.

---

## 2. Overall Description

### 2.1 Product Perspective
The EmberEye Suite 2.0 is a set of desktop applications for vision analytics and sensor fusion. It replaces the 1.x monolithic architecture with a modular one:

- **EmberEye-Base:** Provides common utilities, plugin interfaces, and license management. Installed as a Python package.
- **EmberEye-Studio:** Authoring environment where users create analytics (annotation, training, model export). Exports analytics as `.eapkg` files.
- **EmberEye-Field:** Runtime application that loads analytics from a local Marketplace folder, executes them on live sensor streams, and displays results.
- **Marketplace:** A folder monitored by Field, containing `.eapkg` files. Field provides a UI to import packages from USB or local drives and displays them as interactive cards.

The components communicate via file system (exported packages, license files, configuration JSON). No network communication is required for core functionality, though future extensions may add network licensing.

### 2.2 Product Functions
- **Analytics Authoring (Studio):** Create and export analytics packages.
- **Analytics Import (Field):** Import packages via USB/manual copy; display them as cards.
- **License Management:** Enforce node-locked licenses (hardware ID, device count, per-analytic). Allow merging of multiple license files.
- **Workflow Configuration:** Define analytics dependencies and execution scheduling via visual graph editor (NodeGraphQt) or manual JSON.
- **Analytics Execution:** Run analytics according to the configured DAG and triggers (frame count, time interval) with sequential/parallel policies.
- **Device Simulation:** Use existing PFDS device and RTSP simulators for testing and demonstration.

### 2.3 User Characteristics
- **System Administrators:** Deploy Field in production, manage licenses, configure workflows.
- **Analytics Developers:** Use Studio to create and export analytics.
- **End Users (Operators):** Monitor Field outputs; may adjust basic settings.

### 2.4 Constraints
- **Offline Operation:** All core functions must work without internet connectivity.
- **Python 3.11:** The codebase must be compatible with Python 3.11.
- **PyQt6:** UI must be built with PyQt6.
- **Cross-platform:** Must run on Windows 10/11, Ubuntu 20.04+, macOS 11+.
- **Hardware Binding:** Licenses are tied to machine-specific hardware identifiers (e.g., MAC address, motherboard serial).

### 2.5 Assumptions and Dependencies
- Users have basic familiarity with file operations and JSON editing (for fallback).
- The PFDS device simulator and RTSP simulator are already implemented and functional.
- Third-party libraries (NodeGraphQt, cryptography, networkx) are available via pip and compatible with Python 3.11 and PyQt6.
- The target hardware has sufficient resources to run multiple analytics concurrently (specified in load testing).

---

## 3. Specific Requirements

### 3.1 External Interface Requirements

#### 3.1.1 User Interfaces
- **Main Window (Field):**
  - Tabbed interface with at least: **Analytics** (cards view), **Workflow** (graph editor), **Licenses**, **Settings**.
  - Cards display analytic name, version, status (enabled/disabled), and a checkbox/enable toggle.
  - Workflow tab embeds NodeGraphQt widget with zoom/pan, node creation, connection ports.
  - Licenses tab shows a table of installed licenses (customer, max devices, analytics list, expiry). Includes "Add License" button.
  - Settings tab for configuring watched folder, scheduler defaults, etc.

- **Import Dialog (Field):**
  - Opened via "Import Analytics" button.
  - Allows browsing for a folder (local or USB) and shows progress during import.
  - Reports success/failure for each package.

- **Studio UI (existing):**
  - Enhanced to export analytics as `.eapkg` with metadata.

#### 3.1.2 Hardware Interfaces
- **PFDS Device Simulator:** Provides virtual sensors (IP camera, thermal, flame, smoke, gas). Must be able to simulate multiple devices concurrently for load testing.
- **RTSP Simulator:** Streams video feeds for testing.

#### 3.1.3 Software Interfaces
- **File System:**
  - Watched folder (configurable) for Marketplace.
  - License folder (e.g., `~/EmberEye/Licenses`) monitored for new files.
  - Project folder containing `workflow.json` (DAG configuration).

- **Python Packages:**
  - `cryptography` for license signing/verification.
  - `networkx` for graph algorithms.
  - `NodeGraphQt` for visual graph editing.
  - `pytest`, `pytest-qt`, `locust` for testing.

#### 3.1.4 Communication Interfaces
- **None required** for core offline functionality. Future network licensing may use TCP sockets.

---

### 3.2 Functional Requirements

#### 3.2.1 EmberEye-Base (Core Library)

| ID | Requirement |
|----|-------------|
| F1.1 | Provide a plugin interface (abstract base classes) that all analytics must implement (e.g., `process_frame()`, `configure()`). |
| F1.2 | Implement a hardware ID utility that retrieves a stable machine identifier (e.g., MAC address of primary interface, motherboard serial). |
| F1.3 | Provide logging utilities with structured output (JSON) for debugging and performance monitoring. |
| F1.4 | Define shared data structures for frame data, sensor readings, and analytics results. |

#### 3.2.2 Licensing Module

| ID | Requirement |
|----|-------------|
| F2.1 | Generate RSA key pair (server side) for signing licenses. Embed public key in application. |
| F2.2 | License file format: JSON with fields: `customer` (string), `hardware_id` (string), `max_devices` (int), `analytics` (list of strings), `expiry` (optional ISO date). Signed with private key. |
| F2.3 | On startup, scan license folder for `.lic` files, verify signatures, and merge them: take maximum `max_devices` and union of `analytics`. |
| F2.4 | Provide API to check if a given analytic is licensed (`is_licensed(analytic_id)`). |
| F2.5 | Monitor current device count (from PFDS simulator) and raise alert if exceeding `max_devices`. |
| F2.6 | Provide UI tab in Field (see F5.x) to view licenses and add new ones via file dialog. |

#### 3.2.3 Marketplace & Plugin Management

| ID | Requirement |
|----|-------------|
| F3.1 | Define `.eapkg` as a ZIP archive containing: `metadata.json` (name, version, dependencies, execution hints, required license), Python module(s), and optional assets. |
| F3.2 | Plugin manager monitors watched folder (configurable, default `~/EmberEye/Marketplace`) using `QFileSystemWatcher`. |
| F3.3 | When a new `.eapkg` appears, validate its structure, load metadata, and add to registry. If invalid, log error and ignore. |
| F3.4 | Emit signals when analytics are added/removed so UI can update cards. |
| F3.5 | Provide "Import Analytics" dialog that lets user select any folder, finds all `.eapkg` files, validates them, and copies them to watched folder. Show progress and summary. |
| F3.6 | Cards in UI display analytic name, version, license status (licensed/unlicensed). Enable/disable toggle only if licensed. |
| F3.7 | Provide card display mode selection for banner cards: `Auto` (layout/runtime-managed) and `Manual` (operator-managed visibility). |
| F3.8 | Persist per-card banner visibility settings in configuration and reload them on startup without requiring restart after runtime changes. |
| F3.9 | Apply deterministic display precedence for banner cards: license/availability constraints first, manual visibility second, auto layout fallback last. |
| F3.10 | In `Manual` mode, hidden cards remain hidden even if analytics are active; unlicensed analytics cannot be forced visible. |

#### 3.2.4 Analytics Execution Engine

| ID | Requirement |
|----|-------------|
| F4.1 | Build a DAG from analytics dependencies (defined in metadata and/or user-configured workflow). Use `networkx` for cycle detection and topological sorting. |
| F4.2 | Support two trigger types per analytic: frame count (e.g., every N frames) and time interval (e.g., every T seconds). |
| F4.3 | Allow user to configure execution policy: sequential (run one after another in topological order) or parallel (run independent nodes concurrently using a thread pool). |
| F4.4 | Scheduler: at each frame (or timer tick), evaluate which analytics are ready to run based on triggers and dependencies, and queue them. |
| F4.5 | Provide data passing between analytics: outputs of upstream analytics are available in a shared context for downstream nodes. |
| F4.6 | Log execution start/stop times and errors per analytic. |
| F4.7 | Ensure thread safety for shared data (use Qt signals or locks). |

#### 3.2.5 User Interface (Field & Studio)

| ID | Requirement |
|----|-------------|
| F5.1 | **Analytics Cards View:** Grid of cards showing imported analytics with enable/disable toggle, license indicator, and context menu (configure, remove). |
| F5.2 | **Workflow Editor:** Tab containing NodeGraphQt widget. User can drag nodes (analytics) from a palette, connect outputs to inputs, and set node properties (triggers, execution policy). Graph is saved to `workflow.json`. |
| F5.3 | **Licenses Tab:** Table of installed licenses with columns: Customer, Max Devices, Licensed Analytics, Expiry. Buttons: "Add License" (opens file dialog to select `.lic` files). Current device count displayed. |
| F5.4 | **Settings Tab:** Options to change watched folder path, license folder path, scheduler thread pool size, and logging level. |
| F5.5 | **Fallback JSON Support:** The workflow editor reads/writes `workflow.json`. If the file is manually edited, the app validates it on load; if invalid, shows error and falls back to last valid state. |
| F5.6 | **Studio Export:** Add menu option "Export as Analytics Package" that packages current analytic (model, metadata, code) into `.eapkg` with a signed manifest (optional). |
| F5.7 | **Banner Card Controls:** Provide Field UI controls for per-card on/off visibility and a mode selector (`Auto`/`Manual`) for banner display. |
| F5.8 | **Multi-Analytics Banner Composition:** When multiple analytics are active, compose banner cards using deterministic priority/severity rules under constrained width. |
| F5.9 | **Critical Card Pinning:** Safety-critical cards (alarm/emergency) must remain visible and non-evictable when overflow management is applied. |
| F5.10 | **Overflow Summary Card:** If active cards exceed visible capacity, show a summary card (for example `+N active analytics`) with drill-down to full active list. |
| F5.11 | **Conflicting Slot Resolution:** If multiple analytics target the same banner semantic slot, resolve using deterministic merge rules and expose the active source in UI details. |

---

### 3.3 Non-Functional Requirements

#### 3.3.1 Performance

| ID | Requirement |
|----|-------------|
| N1.1 | Load time for 50 analytics from Marketplace ≤ 5 seconds (on SSD). |
| N1.2 | Scheduler overhead ≤ 2 ms per frame. |
| N1.3 | Parallel execution of up to 10 CPU-bound analytics should not cause frame drops below 30 fps on reference hardware (specified in load test plan). |
| N1.4 | License validation (RSA verify) ≤ 100 ms per license file. |

#### 3.3.2 Security

| ID | Requirement |
|----|-------------|
| N2.1 | License signatures must be generated with RSA-2048 or stronger. Private key stored securely on build server. |
| N2.2 | Hardware ID should be resistant to spoofing (use multiple sources if possible). |
| N2.3 | Plugin loading: analytics run in same process; ensure they cannot access sensitive files (rely on Python sandboxing). Future: consider subprocess isolation. |

#### 3.3.3 Reliability

| ID | Requirement |
|----|-------------|
| N3.1 | The system must handle invalid analytics packages gracefully (ignore, log, notify user). |
| N3.2 | If a license expires or device count exceeds limit, stop affected analytics and alert user. |
| N3.3 | Crash recovery: On restart, reload last workflow and resume monitoring. |

#### 3.3.4 Usability

| ID | Requirement |
|----|-------------|
| N4.1 | All user-visible strings must be in English (localization possible later). |
| N4.2 | Tooltips and help texts available for complex settings. |
| N4.3 | Dependency editor should have undo/redo functionality (provided by NodeGraphQt). |

#### 3.3.5 Maintainability

| ID | Requirement |
|----|-------------|
| N5.1 | Codebase must follow PEP 8 style guidelines. |
| N5.2 | Unit test coverage ≥ 80% for core modules (Base, licensing, plugin manager, scheduler). |
| N5.3 | Use type hints throughout. |

#### 3.3.6 Portability

| ID | Requirement |
|----|-------------|
| N6.1 | All file paths must use `os.path` or `pathlib` for cross-platform compatibility. |
| N6.2 | Hardware ID retrieval must have platform-specific implementations (Windows, Linux, macOS). |
| N6.3 | UI must adapt to different screen resolutions (use layouts, not fixed geometries). |

---

## 4. Appendices

### 4.1 Glossary

| Term | Definition |
|------|------------|
| **EAPKG** | EmberEye Analytics Package – a ZIP archive containing an analytic module, metadata, and optional assets. |
| **Node-locked license** | A license tied to a specific machine via hardware identifiers (MAC address, motherboard serial, etc.). |
| **PFDS** | Physical Fire Detection System – the hardware suite with sensors (cameras, thermal, gas, etc.). |
| **DAG** | Directed Acyclic Graph – used to model analytics execution dependencies. |
| **NodeGraphQt** | Open-source PyQt-based library for visual node graph editing. |
| **Marketplace** | A local folder monitored by Field that holds `.eapkg` files available for use. |

---

### 4.2 Use Cases

#### UC-1: Import Analytics Package

| Field | Detail |
|-------|--------|
| **Use Case ID** | UC-1 |
| **Name** | Import Analytics Package |
| **Actor** | Field User (Operator) |
| **Precondition** | A valid `.eapkg` file exists on a USB drive or local folder. |
| **Trigger** | User clicks the "Import Analytics" button in the Field toolbar. |

**Main Flow:**
1. User clicks "Import Analytics" button.
2. System opens a folder browser dialog.
3. User selects the folder containing `.eapkg` files.
4. System scans the folder, lists found packages, and displays a progress bar.
5. For each package, system validates structure and copies it to the Marketplace folder.
6. System refreshes the Analytics Cards view; a new card appears for each imported analytic.
7. System displays an import summary (success count, failure count).

**Alternate Flow – Corrupt Package:**
- At step 5, if a package fails validation, system logs the error, skips the package, and continues with remaining packages.
- Final summary includes the names of failed packages and error reasons.

**Alternate Flow – Duplicate Package:**
- At step 5, if a package with the same ID and version already exists, system skips it and reports a "duplicate" status in the summary.

**Postcondition:** Valid packages are available in the Marketplace folder and visible in the Analytics Cards view.

---

#### UC-2: Add License File

| Field | Detail |
|-------|--------|
| **Use Case ID** | UC-2 |
| **Name** | Add License File |
| **Actor** | Administrator |
| **Precondition** | A signed license file (`.lic`) has been received from the license authority. Field application is running. |
| **Trigger** | User navigates to the "Licenses" tab and clicks "Add License". |

**Main Flow:**
1. User navigates to the "Licenses" tab.
2. User clicks the "Add License" button.
3. System opens a file dialog filtered to `.lic` files.
4. User selects the license file.
5. System copies the file to the configured license folder.
6. License manager detects the new file via `QFileSystemWatcher` and reloads.
7. System verifies the RSA signature and parses the license fields.
8. System merges the new license with existing ones (max of `max_devices`, union of `analytics`).
9. UI refreshes the license table with the new entry and updated totals.
10. Current device count is re-evaluated against the updated `max_devices` limit.

**Alternate Flow – Invalid Signature:**
- At step 7, if the signature verification fails, system displays an error dialog: "Invalid license file. The file could not be verified."
- The file is not copied to the license folder. No state changes.

**Alternate Flow – Expired License:**
- At step 7, if the `expiry` date is in the past, system displays a warning: "License has expired" and adds it to the table with an "Expired" status indicator.

**Postcondition:** The new license is active and its analytics are available for use.

---

#### UC-3: Configure Workflow Dependencies

| Field | Detail |
|-------|--------|
| **Use Case ID** | UC-3 |
| **Name** | Configure Workflow Dependencies |
| **Actor** | Administrator or Analytics Developer |
| **Precondition** | At least two analytics are imported and licensed. Field application is running. |
| **Trigger** | User opens the "Workflow" tab. |

**Main Flow:**
1. User opens the "Workflow" tab.
2. System displays the NodeGraphQt canvas. Available analytics appear in a node palette on the left.
3. User drags analytics nodes from the palette onto the canvas.
4. User draws a connection from the output port of one node to the input port of another, defining a dependency.
5. User double-clicks a node to open its properties panel and configures: trigger type (`every_n_frames` or `every_seconds`), trigger value, and execution policy (sequential or parallel).
6. User clicks "Save Workflow".
7. System validates the graph: checks for cycles using `networkx` cycle detection.
8. System saves the validated graph to `workflow.json` in the project folder.
9. System confirms save with a status message.

**Alternate Flow – Cycle Detected:**
- At step 7, if a cycle is detected, system highlights the offending nodes/edges in red and displays an error: "Invalid workflow: cycle detected between [Node A] and [Node B]."
- The save is blocked. User must resolve the cycle before saving.

**Alternate Flow – Load Existing Workflow:**
- On tab open (step 1), if a `workflow.json` exists, system loads and renders it in the canvas automatically.
- If `workflow.json` is invalid, system displays an error and opens an empty canvas.

**Postcondition:** `workflow.json` reflects the configured DAG and is used by the scheduler on next start/reload.

---

#### UC-4: Run Field with Active Analytics

| Field | Detail |
|-------|--------|
| **Use Case ID** | UC-4 |
| **Name** | Run Field with Active Analytics |
| **Actor** | Field User (Operator) |
| **Precondition** | A workflow is saved (`workflow.json` exists); at least one analytic is enabled and licensed; PFDS devices are connected or simulated. |
| **Trigger** | User starts the Field application (or clicks "Start Monitoring"). |

**Main Flow:**
1. User starts the Field application.
2. System loads `workflow.json` and rebuilds the execution DAG.
3. System initializes PFDS device connections and begins frame acquisition from camera/sensor streams.
4. Scheduler starts and evaluates trigger conditions on each frame tick and timer event.
5. Analytics whose dependencies are satisfied and trigger conditions are met are queued for execution.
6. Analytics execute in the configured order (sequential or parallel via thread pool).
7. Results from each analytic are written to the shared execution context.
8. Downstream analytics consume upstream results from the context.
9. Final results (e.g., detection overlays, alerts, logs) are displayed in the Field UI.
10. Execution timestamps and any errors are logged per analytic.

**Alternate Flow – License Limit Exceeded:**
- At any point during step 6, if the active device count exceeds `max_devices`, the system disables analytics on the excess devices, emits an alert in the UI: "Device limit exceeded. X analytics have been paused."
- Audit log entry created.

**Alternate Flow – Analytic Runtime Error:**
- At step 6, if an analytic raises an exception, the scheduler catches it, logs the error with traceback, and marks the analytic as "error" state.
- Downstream analytics that depend on it are skipped for that cycle.
- The error is surfaced in the UI with a notification.

**Alternate Flow – Invalid Workflow on Load:**
- At step 2, if `workflow.json` is corrupt or invalid, system shows an error dialog and falls back to the last known valid state (or an empty workflow if no prior valid state exists).

**Postcondition:** Analytics are running, results are displayed, execution is logged.

---

#### UC-5: Export Analytics Package from Studio

| Field | Detail |
|-------|--------|
| **Use Case ID** | UC-5 |
| **Name** | Export Analytics Package from Studio |
| **Actor** | Analytics Developer |
| **Precondition** | An analytic has been authored in Studio (model trained, code written, metadata configured). |
| **Trigger** | User selects "Export as Analytics Package" from the Studio File menu. |

**Main Flow:**
1. User selects "Export as Analytics Package" from the menu.
2. System opens the Export dialog with pre-filled fields from the analytic's metadata (name, version, description, required license ID).
3. User reviews and confirms metadata fields (can edit version, description, execution hints).
4. User selects output destination folder.
5. System assembles the `.eapkg` ZIP archive:
   - `metadata.json` with all metadata fields.
   - Python module(s) for the analytic.
   - Trained model file(s) and any required assets.
6. System writes the ZIP to the destination folder as `<name>-<version>.eapkg`.
7. System displays a success confirmation with the output file path.

**Alternate Flow – Missing Required Fields:**
- At step 3, if required metadata fields (name, version, required license) are missing, system highlights the missing fields and blocks export until resolved.

**Alternate Flow – Output Folder Not Writable:**
- At step 6, if the destination folder cannot be written to, system shows an error: "Cannot write to destination. Check permissions."

**Postcondition:** A valid `.eapkg` file is created and ready for distribution or direct import into Field.

---

**End of Document**
