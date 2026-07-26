"""Generate privacy-safe CycloneDX inventories for release dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "sbom")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)

    python_path = output / "python-production.cdx.json"
    frontend_path = output / "frontend-production.cdx.json"
    if not _generate_python_sbom(python_path):
        return 1
    if not _generate_frontend_sbom(frontend_path):
        return 1

    artifacts = []
    for path in (python_path, frontend_path):
        component_count = _validated_component_count(path)
        if component_count is None:
            return 1
        artifacts.append(
            {
                "path": path.name,
                "components": component_count,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    manifest = {
        "schema_version": 1,
        "app": "Thought Pins",
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "SBOM generation passed: "
        + ", ".join(f"{item['path']} ({item['components']} components)" for item in artifacts)
    )
    return 0


def _generate_python_sbom(destination: Path) -> bool:
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(ROOT / "requirements-prod.lock"),
        "--require-hashes",
        "--disable-pip",
        "--vulnerability-service",
        "osv",
        "--cache-dir",
        str(ROOT / ".tmp" / "pip-audit-cache"),
        "--progress-spinner",
        "off",
        "--timeout",
        "30",
        "--format",
        "cyclonedx-json",
        "--output",
        str(destination),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        print("SBOM generation failed: Python dependency audit did not pass")
        return False
    return True


def _generate_frontend_sbom(destination: Path) -> bool:
    npm = shutil.which("npm")
    if npm is None:
        print("SBOM generation failed: npm is unavailable")
        return False
    completed = subprocess.run(
        [
            npm,
            "sbom",
            "--omit=dev",
            "--package-lock-only",
            "--sbom-format=cyclonedx",
            "--sbom-type=application",
        ],
        cwd=FRONTEND,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print("SBOM generation failed: frontend inventory could not be generated")
        if completed.stderr:
            print(completed.stderr.strip()[:500])
        return False
    destination.write_text(completed.stdout, encoding="utf-8")
    return True


def _validated_component_count(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"SBOM generation failed: {path.name} is not valid JSON ({exc})")
        return None
    if not isinstance(payload, dict) or payload.get("bomFormat") != "CycloneDX":
        print(f"SBOM generation failed: {path.name} is not a CycloneDX document")
        return None
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        print(f"SBOM generation failed: {path.name} contains no components")
        return None
    serialized = json.dumps(payload).lower()
    if any(marker in serialized for marker in ("c:\\users\\", "c:/users/", "/users/")):
        print(f"SBOM generation failed: {path.name} contains a local user path")
        return None
    return len(components)


if __name__ == "__main__":
    raise SystemExit(main())
