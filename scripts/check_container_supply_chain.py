"""Enforce immutable container inputs and a non-root application runtime."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST_PATTERN = re.compile(r"@sha256:[0-9a-f]{64}(?:\s|$)")


def main() -> int:
    findings: list[str] = []
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerignore_lines = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    from_lines = [line.strip() for line in dockerfile.splitlines() if line.strip().startswith("FROM ")]
    if len(from_lines) < 2:
        findings.append("Dockerfile must contain separate web-build and Python runtime stages")
    for line in from_lines:
        if not DIGEST_PATTERN.search(line.replace(" AS ", " ")):
            findings.append(f"Dockerfile base image is not pinned by SHA-256 digest: {line}")

    image_lines = [line.strip() for line in compose.splitlines() if line.strip().startswith("image:")]
    for line in image_lines:
        if not DIGEST_PATTERN.search(line):
            findings.append(f"Compose service image is not pinned by SHA-256 digest: {line}")

    for marker in [
        "COPY requirements-prod.lock ./",
        "pip install --no-cache-dir --require-hashes -r requirements-prod.lock",
        "COPY frontend/public ./public",
        "COPY frontend/scripts/build.mjs ./scripts/build.mjs",
        "USER 10001:10001",
        "PYTHONDONTWRITEBYTECODE=1",
        "HEALTHCHECK",
    ]:
        if marker not in dockerfile:
            findings.append(f"Dockerfile is missing production hardening marker: {marker}")

    if "vault" in dockerignore_lines:
        findings.append(".dockerignore must not exclude the src/thoughtpins/vault package")
    if "vault/**" not in dockerignore_lines:
        findings.append(".dockerignore must exclude only the root vault runtime tree")

    if findings:
        print("Container supply-chain check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"Container supply-chain check passed: {len(from_lines) + len(image_lines)} immutable images verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
