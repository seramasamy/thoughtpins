from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_compose_rehearsal.ps1"
PY_SCRIPT = ROOT / "scripts" / "run_compose_rehearsal.py"


def test_compose_rehearsal_teardown_is_project_scoped() -> None:
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "docker compose -p $ProjectName down" in text
    assert "docker compose down" not in text.replace("docker compose -p $ProjectName down", "")
    assert "down -v" not in text
    assert "--remove-orphans" not in text
    assert "Stop-Process" not in text
    assert "taskkill" not in text.lower()


def test_compose_rehearsal_rejects_generic_project_names() -> None:
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "Assert-SafeComposeProjectName" in text
    assert "^thoughtpins-[a-z0-9][a-z0-9-]{0,50}$" in text
    assert "teardown cannot target unrelated Compose projects" in text


def test_python_compose_rehearsal_teardown_is_project_scoped() -> None:
    text = PY_SCRIPT.read_text(encoding="utf-8-sig")
    assert '"compose", "-p", self.args.project_name' in text
    assert '["down"]' in text
    assert "down -v" not in text
    assert "--remove-orphans" not in text
    assert "Stop-Process" not in text
    assert "taskkill" not in text.lower()


def test_python_compose_rehearsal_rejects_generic_project_names() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_compose_rehearsal", PY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.assert_safe_compose_project_name("thoughtpins-rehearsal")
    module.assert_safe_compose_project_name("thoughtpins-ci-proof")

    for name in ["", "prod", "thoughtpins", "other-thoughtpins", "thoughtpins_unsafe", "thoughtpins-Upper"]:
        try:
            module.assert_safe_compose_project_name(name)
        except ValueError as exc:
            assert "teardown cannot target unrelated Compose projects" in str(exc) or "cannot be empty" in str(exc)
        else:
            raise AssertionError(f"unsafe project name accepted: {name}")

    local_command = module.docker_command("")
    assert len(local_command) == 1
    if sys.platform == "win32":
        assert module.docker_command("Ubuntu-22.04") == [
            "wsl.exe",
            "-d",
            "Ubuntu-22.04",
            "-u",
            "root",
            "--",
            "docker",
        ]
        for distro in ["", "../Ubuntu", "Ubuntu 22.04", "Ubuntu;docker"]:
            if not distro:
                continue
            try:
                module.docker_command(distro)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe WSL distribution name accepted: {distro}")


def test_python_compose_rehearsal_uses_external_proof_schema_markers() -> None:
    text = PY_SCRIPT.read_text(encoding="utf-8-sig")
    for marker in [
        "docker compose config",
        "production_parity_check.py --strict-api --with-postgres-rls",
        "smoke_api.py",
        "smoke_restore_backup.py",
        "compose-rehearsal-",
        "stopped_compose_project",
    ]:
        assert marker in text
