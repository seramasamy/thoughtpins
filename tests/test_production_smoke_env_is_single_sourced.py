"""CI and the local gate must validate the same production shape.

Both need to ask whether a configuration would be allowed to serve production
traffic, without a real production environment to ask about. They used to answer
it from two hand-maintained lists — one in `release_check.py`, one inlined in
the workflow YAML — which had drifted by twenty-six keys. Nobody noticed until a
newly required setting was added to one list and CI failed on a rule the local
gate passed.

A second copy of that environment is the defect, so these assert there is only
one and that both callers reach it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def smoke_step() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index("- name: Production configuration smoke")
    remainder = text[start:]
    # The step ends at the next step, or at the next job when it is the last
    # step in this one. Without the second bound this runs on into the postgres
    # job and reads its service credentials as if they were the step's.
    next_job = re.search(r"\n  [a-z][a-z0-9_-]*:", remainder[1:])
    ends = [
        offset
        for offset in (
            remainder.find("\n      - name:", 1),
            next_job.start() + 1 if next_job else -1,
        )
        if offset != -1
    ]
    return remainder[: min(ends)] if ends else remainder


def test_the_workflow_does_not_carry_its_own_copy_of_the_environment(smoke_step):
    """An inline env block here is the drift, so its absence is the contract."""
    inline_keys = re.findall(r"^\s+([A-Z][A-Z0-9_]{2,}):", smoke_step, re.M)

    assert not inline_keys, (
        "the production smoke step re-declares environment values in YAML: "
        f"{sorted(set(inline_keys))}. Put them in scripts/production_smoke_env.py "
        "so the local release gate validates the same shape."
    )


def test_the_workflow_runs_the_shared_checker(smoke_step):
    assert "scripts/check_production_config_shape.py" in smoke_step, (
        "the production smoke step must run the shared checker, not validate_production.py directly"
    )


def test_the_release_gate_uses_the_same_definition():
    """The local gate must not fork its own copy back off."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util

    from production_smoke_env import production_smoke_env

    spec = importlib.util.spec_from_file_location("release_check_probe", ROOT / "scripts" / "release_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_check_probe"] = module
    spec.loader.exec_module(module)

    shared = production_smoke_env()
    gate = module._production_check_env()

    # Secrets are generated per call, so compare the keys and the settled values.
    assert set(shared) == set(gate)
    volatile = {"API_KEY", "JWT_SECRET", "LLM_API_KEY", "OPENAI_API_KEY", "QDRANT_API_KEY", "DATA_ENCRYPTION_KEY"}
    for key in set(shared) - volatile:
        assert shared[key] == gate[key], f"{key} differs between the shared definition and the release gate"


def test_the_shared_environment_actually_satisfies_production_rules():
    """A shape that cannot pass validation is not a useful single source."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import subprocess

    from production_smoke_env import production_smoke_env

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_production.py")],
        cwd=ROOT,
        env=production_smoke_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, f"the shared production shape does not validate:\n{completed.stdout}"
