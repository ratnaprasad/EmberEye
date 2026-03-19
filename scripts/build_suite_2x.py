#!/usr/bin/env python3
"""Build EmberEye 2.x suite artifacts (Field + Studio) using one command.

This script is the canonical build entrypoint for 2.x development.
It orchestrates legacy per-app builders with an explicit compatibility flag
and emits a suite manifest under dist/suite-2x/.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


def ensure_output_dir(clean: bool) -> Path:
    out_dir = ROOT / "dist" / "suite-2x"
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def build_field(mode: str, build_installer: bool) -> Path:
    env = os.environ.copy()
    env["EMBEREYE_ALLOW_LEGACY_BUILD"] = "1"
    cmd = [sys.executable, str(ROOT / "build_field_onefile.py"), "--mode", mode]
    if build_installer:
        cmd.append("--installer")
    run(cmd, env=env)

    if mode == "onedir":
        artifact = ROOT / "dist" / "EmberEye-Field-GPU"
    else:
        artifact = ROOT / "dist" / "EmberEye-Field-OneFile.exe"

    if not artifact.exists():
        raise FileNotFoundError(f"Expected field artifact missing: {artifact}")
    return artifact


def build_studio() -> Path:
    env = os.environ.copy()
    env["EMBEREYE_ALLOW_LEGACY_BUILD"] = "1"
    cmd = [sys.executable, str(ROOT / "embereye-studio" / "build_installer.py")]
    run(cmd, env=env)

    artifact = ROOT / "embereye-studio" / "dist" / "EmberEyeStudio.exe"
    if not artifact.exists():
        raise FileNotFoundError(f"Expected studio artifact missing: {artifact}")
    return artifact


def copy_artifact(src: Path, out_dir: Path, label: str) -> str:
    target = out_dir / f"{label}-{src.name}"
    if src.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
    else:
        shutil.copy2(src, target)
    return str(target.relative_to(ROOT))


def write_manifest(out_dir: Path, field_artifact: Path, studio_artifact: Path) -> None:
    from embereye import BASE_VERSION, STUDIO_VERSION, FIELD_VERSION, SUITE_RELEASE

    manifest = {
        "suite": "EmberEye",
        "line": "2.x",
        "baseVersion": BASE_VERSION,
        "studioVersion": STUDIO_VERSION,
        "fieldVersion": FIELD_VERSION,
        "suiteMarker": SUITE_RELEASE,
        "artifacts": {
            "field": copy_artifact(field_artifact, out_dir, "field"),
            "studio": copy_artifact(studio_artifact, out_dir, "studio"),
        },
    }
    manifest_path = out_dir / "suite-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[OK] Wrote manifest: {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build EmberEye suite for 2.x")
    parser.add_argument(
        "--field-mode",
        choices=["onedir", "onefile"],
        default="onedir",
        help="Field build mode (onedir recommended for GPU workflows).",
    )
    parser.add_argument(
        "--field-installer",
        action="store_true",
        help="Also build Field installer (requires Inno Setup ISCC.exe).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean suite-2x output directory before writing artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = ensure_output_dir(clean=args.clean)

    print("=" * 70)
    print("EmberEye Suite 2.x Builder")
    print("=" * 70)
    print(f"Workspace: {ROOT}")
    print(f"Output:    {out_dir}")

    field_artifact = build_field(mode=args.field_mode, build_installer=args.field_installer)
    studio_artifact = build_studio()
    write_manifest(out_dir, field_artifact, studio_artifact)

    print("\n[COMPLETE] Suite build successful.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
