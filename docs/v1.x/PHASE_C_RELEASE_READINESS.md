# Phase C Release Readiness

Date: 2026-03-08
Status: Approved Baseline
Scope: Serial-first operations hardening release gates for EmberHawk integration.

## Go/No-Go Gates

All gates must pass for release approval.

1. Build and Core Regression
- `py_compile` passes for manager, main window, TCP servers, and field tests.
- Required test scripts pass:
  - `tests/field/run_device_access_audit_test.py`
  - `tests/field/run_bulk_reconcile_test.py`
  - `tests/field/run_bulk_reconcile_dry_run_test.py`
  - `tests/field/run_device_gating_matrix_test.py`
  - `tests/field/run_identity_churn_soak_test.py`
  - `tests/smoke_simulator_commands.py`

2. SLO Thresholds (24h pre-release soak)
- `embereye_scheduled_reconcile_errors_total` delta: `0`
- `embereye_scheduled_reconcile_disabled_total` delta: `0`
- `embereye_scheduled_reconcile_unmatched_total / attempted` ratio: `<= 0.10`
- Device packet drop alert rate (`ops_alert` high-rate events): `<= 2/hour`
- Device command failure ratio: `<= 1%` during stable network runs

3. Audit and Traceability
- Access mutations append to `logs/device_audit.jsonl` with:
  - actor
  - reason
  - old/new authorization state
  - old/new link state
- Reconciliation actions append telemetry in `logs/device_telemetry.jsonl`.

4. Operator Workflow Validation
- Dry run preview works and does not mutate DB.
- Reconcile report export works in JSON and CSV.
- Bulk reconcile updates pending list and emits summary telemetry.

## Pre-Release Execution Checklist

1. Enable schedule in config for soak run.
2. Run identity churn soak test with representative device scale.
3. Capture `/metrics` snapshot and verify scheduled reconcile counters.
4. Review audit and telemetry logs for at least one full reconcile cycle.
5. Execute rollback drill (below) in staging.

## Rollback Playbook

Trigger rollback if any of these occur:
- Scheduled reconcile auto-disables (`embereye_scheduled_reconcile_disabled_total` increments).
- Reconcile exception bursts continue after restart.
- Unexpected unauthorized/unlinked drift in production.

Rollback steps:
1. Disable scheduled reconcile:
- Set `reconcile_schedule_enabled=false` in config.
2. Restart app process.
3. Verify no new `scheduled_reconcile_run` events are emitted.
4. Continue using manual operator workflow:
- `Dry Run Pending`
- `Export Reconcile Report`
- `Bulk Reconcile Pending`
5. Preserve artifacts for investigation:
- `logs/device_telemetry.jsonl`
- `logs/device_audit.jsonl`
- `logs/tcp_debug.log`
- `logs/tcp_errors.log`

## Release Decision Record

- Decision date:
- Approver:
- Environment:
- Result: GO / NO-GO
- Notes:
