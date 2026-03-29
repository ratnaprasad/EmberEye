# EmberEye License Signing and Enforcement Guide

This guide documents the new licensing foundation that supports:

- Hardware ID derivation
- Signature verification with RSA public/private keys
- Expiry-date validation
- Development-safe bypass mode and strict enforcement mode

## 1. Generate a Signed `.lic` File

Use the CLI entrypoint:

```bash
embereye-license-sign \
  --customer "Acme Safety" \
  --private-key /path/to/private_key.pem \
  --output /path/to/licenses/acme.lic \
  --hardware-id <target_hardware_id> \
  --max-devices 5 \
  --expiry 2028-12-31 \
  --analytic fire \
  --analytic ppe
```

Alternative module form:

```bash
python -m embereye_base.core.licensing.cli \
  --customer "Acme Safety" \
  --private-key /path/to/private_key.pem \
  --output /path/to/licenses/acme.lic \
  --hardware-id <target_hardware_id> \
  --max-devices 5 \
  --expiry 2028-12-31 \
  --analytic fire
```

Notes:

- `--analytic` is repeatable.
- `--expiry` must be ISO date format: `YYYY-MM-DD`.
- Generated license JSON includes a base64 RSA signature.

## 2. Public Key Placement

By default, the manager expects the public key at:

- `${EMBEREYE_HOME}/license_public_key.pem`
- If `EMBEREYE_HOME` is not set: `~/.embereye/license_public_key.pem`

You can override it per manager instance with `public_key_path`.

## 3. Runtime Enforcement Flags

`LicenseManager` now supports strict or development-safe behavior:

- `enforce_hardware_id=False` by default
- `enforce_signature=False` by default
- `enforce_expiry=False` by default

Example strict mode:

```python
from embereye_base.core.licensing import LicenseManager

manager = LicenseManager(
    allow_all=False,
    enforce_hardware_id=True,
    enforce_signature=True,
    enforce_expiry=True,
)
state = manager.refresh_from_directory()
```

## 4. Strict vs Bypass Behavior

In bypass mode (`False`):

- Mismatch/invalid conditions are tracked in diagnostics fields.
- License can still be loaded for development continuity.

In strict mode (`True`):

- Invalid/mismatched/expired licenses are rejected.
- Rejections appear in `state.invalid_files`.

## 5. Useful State Diagnostics

After `refresh_from_directory()`, inspect:

- `state.invalid_files`
- `state.mismatched_files`
- `state.signature_issues`
- `state.expiry_issues`
- `state.loaded_files` (per-file status details)

## 6. Status Semantics

Per-file status values include:

- `signature-verified`
- `unsigned-development`
- `signature-invalid-bypassed`
- `signature-unverified-no-public-key`
- combinations with suffixes like `-expired-bypassed` and `-hardware-mismatch-bypassed`

These statuses are intended for UI/admin visibility and migration diagnostics.
