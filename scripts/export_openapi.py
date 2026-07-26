"""Export or check the generated Thought Pins OpenAPI contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.api import app

DEFAULT_CONTRACT = ROOT / "contracts" / "openapi" / "thoughtpins-v1.openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="Write to an explicit path instead of the canonical contract")
    parser.add_argument(
        "--check", action="store_true", help="Fail if the generated contract differs from the committed file"
    )
    parser.add_argument(
        "--update", action="store_true", help="Replace the committed contract after an intentional API change"
    )
    args = parser.parse_args()
    if args.check and (args.update or args.out):
        parser.error("--check cannot be combined with --update or --out")

    spec = app.openapi()
    _validate(spec)

    content = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if args.check:
        if not DEFAULT_CONTRACT.exists():
            print(f"Committed OpenAPI contract is missing: {DEFAULT_CONTRACT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        existing = DEFAULT_CONTRACT.read_text(encoding="utf-8")
        if existing != content:
            print(
                "OpenAPI contract drift detected. Review the API change and run "
                "`python scripts/export_openapi.py --update` if it is intentional.",
                file=sys.stderr,
            )
            return 1
        print(f"OpenAPI contract check passed: sha256:{digest}")
        return 0

    out = Path(args.out) if args.out else DEFAULT_CONTRACT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"OpenAPI exported: {out} ({len(spec.get('paths', {}))} paths, sha256:{digest})")
    return 0


def _validate(spec: dict) -> None:
    required_paths = {
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/entries",
        "/v1/jobs",
        "/v1/jobs/{job_id}",
        "/v1/jobs/{job_id}/retry",
        "/v1/jobs/{job_id}/cancel",
        "/v1/import/obsidian",
        "/v1/export/vault/download",
        "/v1/health/deep",
        "/v1/client-config",
        "/v1/devices",
        "/v1/errors",
        "/v1/legal/acceptances",
        "/v1/me",
        "/v1/preferences",
        "/v1/sessions",
        "/v1/sessions/{session_id}",
        "/v1/sessions/revoke-others",
    }
    missing = sorted(required_paths - set(spec.get("paths", {})))
    if missing:
        raise RuntimeError(f"OpenAPI missing required paths: {missing}")
    schemas = spec.get("components", {}).get("schemas", {})
    if "ErrorEnvelope" not in schemas:
        raise RuntimeError("OpenAPI missing ErrorEnvelope schema")
    chat = spec["paths"]["/v1/chat"]["post"]
    parameters = chat.get("parameters", [])
    if not any(item.get("in") == "header" and item.get("name") == "Idempotency-Key" for item in parameters):
        raise RuntimeError("OpenAPI mutation contract is missing Idempotency-Key")


if __name__ == "__main__":
    raise SystemExit(main())
