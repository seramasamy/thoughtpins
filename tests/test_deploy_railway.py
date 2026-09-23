"""The deploy script ships one pushed commit, never a working tree, and checks it landed.

Every earlier production build was a `railway up` of whatever directory the CLI
was linked to -- the original checkout, which holds uncommitted research files --
and none recorded a commit. These tests use a real throwaway Git repository and
a fake Railway, so they prove what would be uploaded without uploading anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from thoughtpins.build_info import _revision_from_file

ROOT = Path(__file__).resolve().parents[1]


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("deploy_railway", ROOT / "scripts" / "deploy_railway.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deploy = _load_script()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def commit_file(repo: Path, name: str, content: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-qm", f"add {name}")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # A long parametrized node ID exceeds Git/Win32's working-directory limit.
    directory = tmp_path_factory.mktemp("git")
    git(directory, "init", "-qb", "main")
    git(directory, "config", "user.name", "Fixture")
    git(directory, "config", "user.email", "fixture@example.com")
    git(directory, "config", "core.autocrlf", "false")
    commit_file(directory, "Dockerfile", "FROM scratch\n")
    commit_file(directory, "src/thoughtpins/__init__.py", "")
    commit_file(directory, "alembic/versions/0001_initial.py", "# first\n")
    git(directory, "update-ref", "refs/remotes/origin/main", "HEAD")
    return directory


def real_git(command: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, check=False)


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class FakeRailway:
    """Git runs for real; gh and railway answer from scripted state."""

    def __init__(self, *, ci_runs: list[dict[str, Any]], statuses: Sequence[str] = ("BUILDING", "SUCCESS")) -> None:
        self.ci_runs = ci_runs
        self.statuses = list(statuses)
        self.calls: list[tuple[list[str], Path | None]] = []
        self.uploads: list[dict[str, Any]] = []

    def __call__(self, command: Sequence[str], cwd: Path | None) -> subprocess.CompletedProcess[str]:
        command = list(command)
        self.calls.append((command, cwd))
        if command[0] == "git":
            if command[1] == "fetch":
                return completed()
            return real_git(command, cwd)
        if command[:3] == ["gh", "run", "list"]:
            return completed(json.dumps(self.ci_runs))
        if command[:2] == ["railway", "up"]:
            assert cwd is not None
            stamp = cwd / "src" / "thoughtpins" / "_build_info.json"
            message = command[command.index("--message") + 1]
            self.uploads.append(
                {
                    "service": command[command.index("--service") + 1],
                    "files": sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*") if p.is_file()),
                    "stamp": _revision_from_file(stamp),
                    "message": message,
                }
            )
            return completed()
        if command[:3] == ["railway", "deployment", "list"]:
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            deployments = [
                {"id": f"dep-{index}", "status": status, "meta": {"cliMessage": upload["message"]}}
                for index, upload in enumerate(self.uploads)
            ]
            return completed(json.dumps(deployments))
        raise AssertionError(f"unexpected command {command}")


def green(revision: str) -> list[dict[str, Any]]:
    return [
        {
            "databaseId": 7,
            "status": "completed",
            "conclusion": "success",
            "headSha": revision,
            "createdAt": "2026-09-23T00:00:00Z",
        }
    ]


def args(**overrides: Any) -> argparse.Namespace:
    namespace = deploy._parse_args(["--project", "project-id", "--no-fetch"])
    for key, value in overrides.items():
        setattr(namespace, key, value)
    return namespace


def serving(revision: str | None, worker: str | None = None):
    def fetch(url: str) -> dict[str, Any]:
        if url.endswith("/health"):
            return {"status": "ok", "revision": revision}
        return {"status": "ready", "revision": {"api": revision, "worker": worker}}

    return fetch


def test_ci_must_have_passed_for_the_exact_commit():
    sha = "a" * 40
    assert deploy.ci_refusal(green(sha), sha) is None
    assert "no ci.yml run" in (deploy.ci_refusal(green("b" * 40), sha) or "")
    running = [{**green(sha)[0], "status": "in_progress", "conclusion": ""}]
    assert "still in_progress" in (deploy.ci_refusal(running, sha) or "")
    # A later failed rerun outranks an earlier success on the same commit.
    rerun = [*green(sha), {**green(sha)[0], "databaseId": 8, "conclusion": "failure", "createdAt": "2026-09-24"}]
    assert "concluded failure" in (deploy.ci_refusal(rerun, sha) or "")


def test_the_export_is_the_commit_not_the_working_tree(repo, tmp_path):
    revision = git(repo, "rev-parse", "HEAD")
    (repo / "Dockerfile").write_text("FROM uncommitted-edit\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=never-uploaded\n", encoding="utf-8")
    (repo / "research_scratch.py").write_text("print('private')\n", encoding="utf-8")

    stamp = deploy.export_commit(revision, tmp_path / "export", real_git, repo, ref="origin/main")

    export = tmp_path / "export"
    files = sorted(p.relative_to(export).as_posix() for p in export.rglob("*") if p.is_file())
    assert files == [
        "Dockerfile",
        "alembic/versions/0001_initial.py",
        "src/thoughtpins/__init__.py",
        "src/thoughtpins/_build_info.json",
    ]
    assert (export / "Dockerfile").read_text(encoding="utf-8") == "FROM scratch\n"
    assert _revision_from_file(stamp) == revision


def test_a_commit_that_is_not_on_main_is_refused(repo):
    git(repo, "checkout", "-qb", "feature")
    unmerged = commit_file(repo, "feature.txt", "not merged\n")

    with pytest.raises(deploy.DeployRefused, match="not on origin/main"):
        deploy.ensure_on_main(unmerged, real_git, repo)


def test_migrations_added_since_the_deployed_build_stop_the_deploy(repo):
    deployed = git(repo, "rev-parse", "HEAD")
    target = commit_file(repo, "alembic/versions/0002_new_table.py", "# second\n")

    with pytest.raises(deploy.DeployRefused, match="0002_new_table.py"):
        deploy.check_migrations([deployed], target, real_git, repo)
    deploy.check_migrations([target], target, real_git, repo)


def test_operator_confirmation_is_the_only_way_past_new_migrations(repo):
    deployed = git(repo, "rev-parse", "HEAD")
    target = commit_file(repo, "alembic/versions/0002_new_table.py", "# second\n")
    git(repo, "update-ref", "refs/remotes/origin/main", target)
    railway = FakeRailway(ci_runs=green(target))

    with pytest.raises(deploy.DeployRefused, match="0002_new_table.py"):
        deploy.deploy(args(dry_run=True), railway, repo, fetch=serving(deployed, deployed))
    assert deploy.deploy(args(dry_run=True, migrations_applied=True), railway, repo, fetch=serving(None)) == 0


def test_an_unstamped_production_build_needs_an_explicit_baseline(repo):
    revision = git(repo, "rev-parse", "HEAD")

    with pytest.raises(deploy.DeployRefused, match="--since"):
        deploy.check_migrations([None, revision], revision, real_git, repo)


def test_deploy_uploads_the_stamped_export_to_each_service_and_waits_for_the_revision(repo, tmp_path):
    revision = git(repo, "rev-parse", "HEAD")
    railway = FakeRailway(ci_runs=green(revision))

    def fetch(url: str) -> dict[str, Any]:
        # Each service reports the new revision only once it has been uploaded.
        uploaded = {upload["service"] for upload in railway.uploads}
        api = revision if "api" in uploaded else None
        worker = revision if "worker" in uploaded else None
        return {"revision": api} if url.endswith("/health") else {"revision": {"api": api, "worker": worker}}

    result = deploy.deploy(args(since=[revision]), railway, repo, fetch=fetch, sleep=lambda _s: None)

    assert result == 0
    assert [upload["service"] for upload in railway.uploads] == ["api", "worker"]
    for upload in railway.uploads:
        assert upload["stamp"] == revision
        assert ".env" not in upload["files"]
        assert upload["message"].startswith(f"{revision} scripts/deploy_railway.py ")
    up = next(command for command, _ in railway.calls if command[:2] == ["railway", "up"])
    assert "--no-gitignore" in up and up[up.index("--project") + 1] == "project-id"


def test_a_failed_railway_build_is_reported_not_waited_out(repo):
    revision = git(repo, "rev-parse", "HEAD")
    railway = FakeRailway(ci_runs=green(revision), statuses=("BUILDING", "FAILED"))

    with pytest.raises(deploy.DeployRefused, match="ended FAILED"):
        deploy.deploy(
            args(migrations_applied=True), railway, repo, fetch=serving(revision, revision), sleep=lambda _s: None
        )
    assert len(railway.uploads) == 1, "the worker must not deploy after the API build failed"


def test_a_red_ci_run_uploads_nothing(repo):
    revision = git(repo, "rev-parse", "HEAD")
    failed = [{**green(revision)[0], "conclusion": "failure"}]
    railway = FakeRailway(ci_runs=failed)

    with pytest.raises(deploy.DeployRefused, match="concluded failure"):
        deploy.deploy(args(migrations_applied=True), railway, repo, fetch=serving(revision), sleep=lambda _s: None)
    assert railway.uploads == []


def test_dry_run_checks_and_exports_but_uploads_nothing(repo, capsys):
    revision = git(repo, "rev-parse", "HEAD")
    railway = FakeRailway(ci_runs=green(revision))

    result = deploy.deploy(args(dry_run=True), railway, repo, fetch=serving(revision, revision))

    assert result == 0
    assert railway.uploads == []
    assert "Would run: railway up" in capsys.readouterr().out


def test_a_deploy_that_never_serves_the_new_revision_fails():
    ticks = iter(range(0, 10_000, 100))

    with pytest.raises(deploy.DeployRefused, match="still reports revision"):
        deploy.wait_for_revision(
            "api",
            "a" * 40,
            "https://api.example",
            fetch=serving("b" * 40),
            timeout=250,
            sleep=lambda _s: None,
            clock=lambda: float(next(ticks)),
        )
