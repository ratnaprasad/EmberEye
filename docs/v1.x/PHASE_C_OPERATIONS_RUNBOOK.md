# Phase C Operations Runbook

Date: 2026-03-08
Scope: Scheduled reconciliation, audit trail, and ops alerting for EmberHawk serial lifecycle.

Detailed release gates and rollback criteria are documented in:
- `docs/PHASE_C_RELEASE_READINESS.md`

## Features Included

- Scheduled pending-identity reconciliation with cooldown and failure guard.
- Dry-run reconciliation preview and report export (JSON/CSV).
- Device access mutation audit log (`logs/device_audit.jsonl`).
- Device telemetry log (`logs/device_telemetry.jsonl`).
- Prometheus counters for device lifecycle and scheduled reconcile outcomes.

## Configuration Keys

Set these values in stream config.

- `reconcile_schedule_enabled` (bool, default `false`): Enable scheduled reconcile loop.
- `reconcile_interval_s` (float, default `300`): Timer interval for scheduled reconcile checks.
- `reconcile_cooldown_s` (float, default `120`): Minimum seconds between effective reconcile runs.
- `reconcile_max_consecutive_errors` (int, default `3`): Auto-disable threshold.
- `device_alert_window_ms` (int, default `30000`): Ops alert sampling window.
- `device_drop_alert_per_min` (float, default `20`): Packet-drop rate alert threshold.
- `device_command_fail_alert_per_min` (float, default `10`): Command-failure alert threshold.
- `device_alert_cooldown_s` (float, default `60`): Minimum spacing between repeated alerts.
- `operator_id` (string, optional): Cached operator identity for mutation actions.

## Prometheus Metrics

New device metrics:

- `embereye_device_lifecycle_events_total{event,state}`
- `embereye_device_packet_drops_total{reason,state}`
- `embereye_device_commands_total{event,command}`
- `embereye_device_command_failures_total{reason,command}`

Scheduled reconcile metrics:

- `embereye_scheduled_reconcile_runs_total{outcome}`
- `embereye_scheduled_reconcile_bound_total`
- `embereye_scheduled_reconcile_unmatched_total`
- `embereye_scheduled_reconcile_errors_total`
- `embereye_scheduled_reconcile_disabled_total`

## Operator Workflow

1. Open PFDS Device dialog.
2. Run `Dry Run Pending` to preview candidate bindings.
3. Export report if review/approval is needed.
4. Run `Bulk Reconcile Pending` to apply bindings.
5. Verify pending list reduction and audit entries.

## Failure Guard Behavior

- If scheduled reconcile throws exceptions repeatedly or error count crosses threshold, the scheduler auto-disables.
- Auto-disable emits telemetry event `scheduled_reconcile_disabled` and increments `embereye_scheduled_reconcile_disabled_total`.
- Re-enable by setting `reconcile_schedule_enabled=true` and restarting app (or reloading config flow).

## Log Locations

- Device telemetry: `logs/device_telemetry.jsonl`
- Device audit: `logs/device_audit.jsonl`
- TCP debug/errors: `logs/tcp_debug.log`, `logs/tcp_errors.log`

## Recommended Dashboard Panels

- Scheduled reconcile runs by outcome (stacked by `outcome`).
- Scheduled reconcile unmatched total trend.
- Scheduled reconcile errors and disabled counter.
- Device packet drops by reason/state.
- Device command failures by reason.

## Release Gates (Summary)

Before production rollout, confirm:

- Field regression scripts pass (`audit`, `reconcile`, `dry-run`, `gating matrix`, `soak`, and smoke simulators).
- Scheduled reconcile remains healthy (`embereye_scheduled_reconcile_errors_total` and `embereye_scheduled_reconcile_disabled_total` stay flat during soak).
- Unmatched ratio and command-failure rate stay within release thresholds from `docs/PHASE_C_RELEASE_READINESS.md`.
- Rollback drill was executed successfully in staging.

## Soak Test Harness

Identity churn and reconnect storm test:

- Script: `tests/field/run_identity_churn_soak_test.py`
- Example:
	- `python tests/field/run_identity_churn_soak_test.py --devices 60 --rounds 40 --seed 42`

Success criteria:

- No duplicate serial bindings in DB.
- No reconcile errors reported.
- Bound serials remain linked.
