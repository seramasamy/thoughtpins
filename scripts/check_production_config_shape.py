"""Validate production configuration rules against a synthetic production env.

CI used to inline its own copy of that environment next to the step. Keeping a
second list in YAML meant a newly required setting was only added to whichever
copy the author happened to be looking at, and the two had drifted by
twenty-six keys before anyone noticed — the drift only became visible when the
LLM price map became mandatory and CI failed on a rule the local gate passed.

This runs the same validator against the same environment both places use.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from production_smoke_env import production_smoke_env  # noqa: E402


def main() -> int:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_production.py")],
        cwd=ROOT,
        env=production_smoke_env(),
        check=False,
    )
    if completed.returncode != 0:
        print("Production configuration shape check failed.")
        return completed.returncode
    print("Production configuration shape check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
