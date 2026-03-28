from __future__ import annotations

import os
from pathlib import Path


def get_embereye_home() -> Path:
    override = os.environ.get("EMBEREYE_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".embereye"


def get_license_dir(create: bool = True) -> Path:
    license_dir = get_embereye_home() / "licenses"
    if create:
        license_dir.mkdir(parents=True, exist_ok=True)
    return license_dir


def get_license_public_key_path(create_parent: bool = True) -> Path:
    base_dir = get_embereye_home()
    if create_parent:
        base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "license_public_key.pem"
