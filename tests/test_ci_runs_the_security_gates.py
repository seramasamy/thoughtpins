"""A gate that only runs on the maintainer's laptop does not protect the repo.

Two checks have now been added to the local release gate and not to CI: the
production configuration shape, and the dependency audit covering the optional
extras. Both were written in response to a real defect, and both would have gone
on passing locally while pull requests merged without them.

This pins the checks that must run in CI by name. Deriving the list from
whatever the local gate happens to run would make it vacuous — it would accept
the current state as correct, which is the thing being questioned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# Each entry names why removing it from CI would be a regression, not just a
# preference. Anything that guards a tenant boundary, a secret, a published
# artifact, or a known-vulnerable dependency belongs here.
REQUIRED_IN_CI = {
    "scripts/forbidden_scan.py": "old project names and credential-shaped strings in the tree",
    "scripts/check_public_export.py": "private files and secrets reaching a public export",
    "scripts/check_log_privacy.py": "user content leaking into runtime logs",
    "scripts/check_rls_static.py": "tenant isolation coverage in the schema",
    "scripts/check_optional_extra_dependencies.py": "advisories in the 127 packages outside the production lock",
    "scripts/check_dependency_locks.py": "a lock file that no longer matches the declared graph",
    "scripts/check_architecture_budget.py": "core layers importing a transport, and file-size ratchets",
    "scripts/check_production_config_shape.py": "a configuration that would be refused in production",
    "scripts/check_container_supply_chain.py": "an image built from something other than the pinned lock",
}


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.mark.parametrize("script,reason", sorted(REQUIRED_IN_CI.items()))
def test_ci_runs_this_security_gate(workflow_text, script, reason):
    assert script in workflow_text, f"CI does not run {script}, which guards {reason}"


def test_ci_audits_more_than_the_production_lock(workflow_text):
    """The production export is a subset; auditing only it reports a clean subset."""
    assert "requirements-prod.lock" in workflow_text, "the production audit should still run"
    assert "check_optional_extra_dependencies" in workflow_text, (
        "CI audits only the production lock, so a vulnerable optional extra passes unnoticed"
    )
