"""A green main build must include iOS when any part of its push changed iOS."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def commit(repo: Path, name: str) -> str:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-qm", "fixture")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # A full parametrized node ID exceeds Git/Win32's working-directory limit.
    directory = tmp_path_factory.mktemp("git")
    git(directory, "init", "-qb", "main")
    git(directory, "config", "user.name", "Fixture")
    git(directory, "config", "user.email", "fixture@example.com")
    commit(directory, "README.md")
    return directory


def touched(repo: Path, base: str) -> bool:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    step = next(s for s in workflow["jobs"]["ios-changes"]["steps"] if s.get("id") == "check")
    output = repo / "ci-output"
    bash = shutil.which("bash") or "bash"
    if os.name == "nt":
        # Use the Bash shipped with Git instead of the Windows WSL launcher.
        git_bash = Path(shutil.which("git") or "git").resolve().parent.parent / "bin" / "bash.exe"
        if git_bash.is_file():
            bash = str(git_bash)
    subprocess.run(
        [bash, "-euo", "pipefail", "-c", step["run"]],
        cwd=repo,
        check=True,
        env={
            **os.environ,
            "THOUGHTPINS_PUSH_BASE": base,
            "GITHUB_OUTPUT": output.as_posix(),
            "RUNNER_TEMP": repo.as_posix(),
        },
    )
    return output.read_text().strip() == "touched=true"


@pytest.mark.parametrize(
    "path",
    [
        "mobile/ios/Feature.swift",
        "frontend/scripts/native-review-server.mjs",
        ".github/workflows/ios-native-review.yml",
    ],
)
def test_whole_push_includes_changes_before_last_commit(repo: Path, path: str) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, path)
    commit(repo, "docs/final-note.md")
    assert touched(repo, base)


def test_merge_promotion_compares_previous_main_not_first_parent(repo: Path) -> None:
    git(repo, "checkout", "-qb", "feature")
    commit(repo, "mobile/ios/Feature.swift")
    git(repo, "checkout", "-q", "main")
    git(repo, "commit", "--allow-empty", "-qm", "main metadata")
    previous_main = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "feature")
    git(repo, "merge", "--no-ff", "-qm", "promote", "main")
    assert not git(repo, "diff", "--name-only", "HEAD~1", "HEAD")
    assert touched(repo, previous_main)


def test_docs_only_push_does_not_schedule_native(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "docs/note.md")
    assert not touched(repo, base)


def test_archive_requires_both_isolated_device_reviews() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    native = workflow["jobs"]["ios-native"]
    assert native["strategy"]["matrix"]["device_family"] == ["iPhone", "iPad"]
    assert native["strategy"]["fail-fast"] is False
    assert native["uses"] == "./.github/workflows/ios-native-review.yml"
    archive = workflow["jobs"]["ios"]
    assert archive["needs"] == ["ios-native"]
    assert archive["if"] == "always() && needs.ios-native.result == 'success'"


def test_new_branch_without_previous_commit_requires_native(repo: Path) -> None:
    assert touched(repo, "0" * 40)
