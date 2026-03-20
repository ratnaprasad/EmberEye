# EmberHawk Phase A Completion

Date: 2026-03-08
Status: Complete

## Scope Completed

Phase A objective was to shift runtime identity from transient network location to serial-first device identity, while preserving existing command behavior and enabling safe authorization/link gating.

### 1. Packet and Command Contract (Locked)

- Command transport is plain ASCII.
- Command terminator is optional and not required.
- `ALARM_ON` has no device response packet (fire-and-forget).
- `ACK_ON` has no device response packet (fire-and-forget).
- Response-bearing commands include `DEVICE_ID`, `REQUEST1`, and `EEPROM1` flows.

### 2. DB Foundation (Backward Compatible)

The `pfds_devices` schema now supports serial-first operations with compatibility migration at startup.

Added fields:
- `serial_number`
- `is_authorized`
- `is_linked`
- `last_seen_ip`
- `last_seen_at`

Migration behavior:
- Existing deployments keep working without manual DB reset.
- Missing columns are added dynamically.

### 3. Handshake and Identity Binding

Both TCP server implementations now parse and register `#DEVICE_ID` identity packets.

Servers updated:
- `embereye/core/tcp_sensor_server.py`
- `embereye/core/tcp_async_server.py`

Identity behavior:
- Serial is bound to active connection.
- Packet metadata carries serial when known.
- Commands can be routed by serial target.

### 4. Authorization and Link Gating

In `embereye-field/fieldglass/main_window.py`, packet routing for `frame/sensor/eeprom` requires:
- serial identity present,
- serial linked to a managed device,
- `is_authorized = true`,
- `is_linked = true`.

Blocked or pending devices are intentionally excluded from fusion/UI pipeline.

### 5. Serial-First Dispatch Hardening

Dispatch path now prefers `serial_number` as command target.

Additional hardening:
- Threaded server no longer uses implicit single-client fallback when target does not match.
- Command delivery now requires explicit serial/IP resolution.

### 6. Device Dashboard Controls

PFDS/EmberHawk dialogs support identity lifecycle operations:
- view serial, authorization, link, and last seen fields,
- view pending identities (seen by `DEVICE_ID`, not linked),
- bind pending serials to selected device,
- toggle authorized state,
- toggle linked state.

## Validation Summary

Validation executed after Phase A changes:

- `py_compile` passed for updated runtime files.
- Simulator smoke test passed:
  - `tcp_sensor_simulator_v3`: PASS
  - `pfds_simulator`: PASS
- `ALARM_ON` and `ACK_ON` command handling remained intact.

## Next Phase: Phase B

Phase B focus: make serial identity the primary key across all remaining operational surfaces, not only packet ingress and command dispatch.

Planned Phase B work:
1. Replace residual location/IP assumptions in scheduler- and UI-side targeting paths with serial-first lookups.
2. Add explicit pending/ghost states to dashboard flows and status visuals.
3. Add serial-centric telemetry/log dimensions for easier operational tracing.
4. Add integration tests for gated routing (authorized/linked true/false combinations).
5. Add migration-safe admin operations for bulk serial binding and reconciliation.

## Exit Criteria for Phase B

- No command path requires loc/IP as primary identity.
- Dashboard workflows cover pending, linked, unlinked, and unauthorized states.
- Tests verify packet acceptance and drop behavior for all access-state combinations.
- Operational logs can trace packet and command lifecycle by serial end-to-end.

## Phase B Closure Update

Date: 2026-03-08
Status: Closed

Completed in Phase B:
1. Serial-first scheduler/dispatch targeting finalized.
2. Lifecycle states surfaced in dashboard (`pending_identity`, `unlinked`, `unauthorized`, `active`, `ghost`).
3. Serial-centric telemetry/logging completed:
- structured runtime events,
- durable JSONL sink (`logs/device_telemetry.jsonl`),
- Prometheus device lifecycle/command counters.
4. Gating integration coverage added (`tests/field/run_device_gating_matrix_test.py`).
5. Bulk serial reconciliation tooling added:
- manager API `bulk_reconcile_pending_serials`,
- UI action `Bulk Reconcile Pending`,
- validation test `tests/field/run_bulk_reconcile_test.py`.

## Phase C Closure Update

Date: 2026-03-08
Status: Closed

Phase C focus was production operations hardening on top of serial-first runtime.

Planned Phase C work:
1. Add operator alerts and dashboards for new device lifecycle counters.
2. Add audit trail and role-safe controls for authorization/link changes.
3. Add reconciliation dry-run/report export and scheduled reconciliation jobs.
4. Add end-to-end soak tests for multi-device identity churn and reconnect storms.
5. Define release readiness gates (SLO thresholds, rollback playbook, runbook updates).

### Phase C Progress (Final)

Completed:
1. Operator alerts on device error-rate counters.
2. Access-change audit trail with operator identity and mutation reason.
3. Reconciliation dry-run/report export and scheduled reconciliation with failure guard.
4. End-to-end soak tests for multi-device identity churn and reconnect storms.
5. Release readiness gates with explicit SLO thresholds and rollback playbook.

Runbooks:
- `docs/PHASE_C_OPERATIONS_RUNBOOK.md`
- `docs/PHASE_C_RELEASE_READINESS.md`

## Next Phase: Phase D

Recommended Phase D focus: reliability automation and production rollout governance.

## Phase D Status Update

Date: 2026-03-08
Status: In Progress

Completed in Phase D so far:
1. Automated release readiness gate script added (`tests/field/run_release_readiness_gate.py`).
2. CI workflow enforcement added (`.github/workflows/release-readiness-gate.yml`).
3. Rollback drill automation script added (`tests/field/run_rollback_drill.py`).
4. Deployment/checklist docs updated with gate and rollback commands.

Remaining to close Phase D:
1. Run strict gate in an environment with live `/metrics` (without `--allow-missing-metrics`).
2. Execute rollback drill with production-equivalent restart command and archive report evidence.
3. Add release sign-off records (approver + timestamp + report artifacts) per deployment.

## Phase D Closure Update

Date: 2026-03-09
Status: Closed

Closure evidence:
1. Strict release readiness gate passed with live `/metrics`:
- Decision: `GO`
- Artifact: `tests/artifacts/release_readiness_report.json`
- Report timestamp: `2026-03-08T18:37:29.497036+00:00`
2. Rollback drill passed with production-equivalent restart command:
- Command path used: `bash scripts/runtime/start_field.sh`
- Decision: `PASS`
- Artifact: `tests/artifacts/rollback_drill_report.json`
- Report timestamp: `2026-03-08T18:36:22.979270+00:00`
3. Release sign-off record added for this closure run:
- Approver: Pending operator approval
- Environment: Local field stack validation
- Result: `GO` (gate) and `PASS` (rollback)
- Evidence artifacts:
  - `tests/artifacts/release_readiness_report.json`
  - `tests/artifacts/rollback_drill_report.json`

## Phase E Parked (TODO)

Date parked: 2026-03-09
Status: Deferred by operator

TODO backlog for next execution window:
1. Add canary/progressive rollout policy (`5% -> 25% -> 100%`) with automated promotion gates.
2. Add automated rollback orchestration from alert triggers with recorded execution evidence.
3. Formalize SLO/error-budget policy and release blocking on burn-rate breaches.
4. Add command/auth hardening for device control path and dependency CVE release gate.
5. Add data-quality and drift monitoring for sensor payloads and identity mapping stability.
6. Expand observability to end-to-end serial traceability from ingress to command ack/audit.
7. Add scheduled resilience/chaos validation suite for reconnect storms and partial failures.
8. Enforce immutable release governance record per deployment (approver, env, artifacts).
