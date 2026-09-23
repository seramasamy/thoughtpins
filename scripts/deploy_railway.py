"""Deploy exactly one pushed, CI-green commit to Railway, then prove it landed.

`railway up` uploads whatever directory it is run from, committed or not, and
every production deployment on record was made that way. None recorded a
commit, and the checkout the Railway CLI is linked to holds uncommitted
research files. On 23 September 2026 the API was found 14 commits and the
worker 18 commits behind GitHub main, and nothing but free-text deployment
notes said so.

This script removes the working tree from the path entirely:

1. Resolve one commit and require it to be on ``origin/main`` with a green
   ``ci.yml`` run for that exact SHA.
2. Refuse when migrations were added since the builds production is running,
   until the operator confirms they were applied (see the production runbook).
3. Export the commit with ``git archive`` into a temporary directory -- tracked
   files only, never the checkout -- and stamp ``_build_info.json`` into it.
4. Upload that directory to each service and wait for Railway to report the
   deployment it created.
5. Read ``/health`` and ``/ready`` until the API and the worker each report the
   new revision. A successful upload is not treated as a successful deploy.

``--dry-run`` performs every check and builds the export without uploading.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.build_info import BUILD_INFO_FILENAME, build_info_document, normalize_revision

DEFAULT_HEALTH_URL = "https://api.thoughtpins.com"
DEFAULT_SERVICES = ("api", "worker")
MAIN_REF = "origin/main"
MIGRATIONS_PATH = "alembic/versions"
BUILD_INFO_RELATIVE = Path("src") / "thoughtpins" / BUILD_INFO_FILENAME
# Cloudflare answers Python's default signature with 403 / error 1010 on every
# path, which reads like an authentication failure and is not one.
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0"
TERMINAL_FAILURES = {"FAILED", "CRASHED", "REMOVED", "SKIPPED"}

Runner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


class DeployRefused(RuntimeError):
    """A precondition failed; nothing was uploaded because of it."""


@dataclass(frozen=True)
class Target:
    project: str
    environment: str
    services: tuple[str, ...]
    health_url: str


def run(command: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    # Resolve through PATH explicitly: on Windows the Railway CLI is installed as
    # railway.cmd, which CreateProcess will not find from the bare name.
    executable = shutil.which(command[0])
    if executable is None:
        raise DeployRefused(f"{command[0]} is not installed or not on PATH")
    return subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )


def _checked(runner: Runner, command: Sequence[str], cwd: Path | None) -> str:
    result = runner(command, cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise DeployRefused(f"{command[0]} {command[1]} failed: {detail[-1] if detail else result.returncode}")
    return result.stdout.strip()


def resolve_revision(ref: str, runner: Runner, repo: Path) -> str:
    output = _checked(runner, ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo)
    revision = normalize_revision(output)
    if revision is None:
        raise DeployRefused(f"{ref} does not name a commit")
    return revision


def ensure_on_main(revision: str, runner: Runner, repo: Path, main_ref: str = MAIN_REF) -> None:
    result = runner(["git", "merge-base", "--is-ancestor", revision, main_ref], repo)
    if result.returncode != 0:
        raise DeployRefused(
            f"{revision[:12]} is not on {main_ref}. Deploy only what GitHub main holds: push or merge it first."
        )


def ci_refusal(runs: Iterable[dict[str, Any]], revision: str) -> str | None:
    """Why this commit's ci.yml result forbids a deploy, or None when it passed.

    The newest run for the exact SHA decides. Dependabot and heartbeat runs are
    separate workflows and never count; that is why the caller filters to ci.yml.
    """

    matching = [run for run in runs if str(run.get("headSha", "")).lower() == revision]
    if not matching:
        return f"no ci.yml run exists for {revision[:12]}"
    latest = max(matching, key=lambda run: str(run.get("createdAt", "")))
    if latest.get("status") != "completed":
        return f"ci.yml run {latest.get('databaseId')} for {revision[:12]} is still {latest.get('status')}"
    if latest.get("conclusion") != "success":
        return f"ci.yml run {latest.get('databaseId')} for {revision[:12]} concluded {latest.get('conclusion')}"
    return None


def check_ci(revision: str, runner: Runner, repo: Path) -> None:
    output = _checked(
        runner,
        [
            "gh",
            "run",
            "list",
            "--workflow=ci.yml",
            "--commit",
            revision,
            "--json",
            "databaseId,status,conclusion,headSha,createdAt",
            "--limit",
            "20",
        ],
        repo,
    )
    refusal = ci_refusal(json.loads(output or "[]"), revision)
    if refusal:
        raise DeployRefused(refusal)


def added_migrations(baseline: str, revision: str, runner: Runner, repo: Path) -> list[str]:
    if runner(["git", "cat-file", "-e", f"{baseline}^{{commit}}"], repo).returncode != 0:
        raise DeployRefused(f"baseline {baseline[:12]} is not in this clone; fetch it or pass --since explicitly")
    output = _checked(
        runner,
        ["git", "diff", "--name-only", "--diff-filter=A", baseline, revision, "--", MIGRATIONS_PATH],
        repo,
    )
    return sorted(line for line in output.splitlines() if line.endswith(".py"))


def check_migrations(baselines: Sequence[str | None], revision: str, runner: Runner, repo: Path) -> None:
    if any(baseline is None for baseline in baselines):
        raise DeployRefused(
            "production does not report which commit it runs (its build predates revision stamping), so pending "
            "migrations cannot be computed. Pass --since <sha> naming the oldest deployed build from its Railway "
            "deployment note, or --migrations-applied after `alembic upgrade head`."
        )
    added = sorted(
        {path for baseline in baselines if baseline for path in added_migrations(baseline, revision, runner, repo)}
    )
    if added:
        raise DeployRefused(
            "new migrations since the deployed build: "
            + ", ".join(added)
            + ". Apply them first (docs/operations/PRODUCTION_RUNBOOK.md), then rerun with --migrations-applied."
        )


def export_commit(revision: str, destination: Path, runner: Runner, repo: Path, *, ref: str) -> Path:
    """Write the tracked tree of one commit, plus its build record, into destination."""

    destination.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / f"{destination.name}.tar"
    _checked(runner, ["git", "archive", "--format=tar", "-o", str(archive), revision], repo)
    try:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")
    finally:
        archive.unlink(missing_ok=True)
    if not (destination / "Dockerfile").is_file():
        raise DeployRefused(f"{revision[:12]} has no Dockerfile at its root")
    stamp = destination / BUILD_INFO_RELATIVE
    stamp.parent.mkdir(parents=True, exist_ok=True)
    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    stamp.write_text(build_info_document(revision, ref=ref, exported_at_utc=exported_at), encoding="utf-8")
    return stamp


def railway_up_command(target: Target, service: str, message: str) -> list[str]:
    # --no-gitignore: the export holds tracked files only, so there is nothing
    # to filter, and the build stamp is gitignored in the repository precisely
    # so that nobody commits one by hand.
    return [
        "railway",
        "up",
        "--detach",
        "--no-gitignore",
        "--project",
        target.project,
        "--environment",
        target.environment,
        "--service",
        service,
        "--message",
        message,
    ]


def deployment_message(revision: str, nonce: str) -> str:
    # Plain characters only: on Windows the Railway CLI is a .cmd shim, and
    # cmd.exe reinterprets quotes, carets and percent signs in its arguments.
    return f"{revision} scripts/deploy_railway.py {nonce}"


def _deployments(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("deployments", [])
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def find_deployment(payload: Any, nonce: str) -> dict[str, Any] | None:
    for deployment in _deployments(payload):
        meta = deployment.get("meta")
        if isinstance(meta, dict) and nonce in str(meta.get("cliMessage") or ""):
            return deployment
    return None


def wait_for_deployment(
    target: Target,
    service: str,
    nonce: str,
    runner: Runner,
    *,
    timeout: float,
    interval: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    deadline = clock() + timeout
    last_status = "not listed yet"
    while True:
        output = _checked(
            runner,
            [
                "railway",
                "deployment",
                "list",
                "--project",
                target.project,
                "--environment",
                target.environment,
                "--service",
                service,
                "--limit",
                "10",
                "--json",
            ],
            None,
        )
        deployment = find_deployment(json.loads(output or "[]"), nonce)
        if deployment is not None:
            last_status = str(deployment.get("status") or "UNKNOWN")
            if last_status == "SUCCESS":
                return str(deployment.get("id"))
            if last_status in TERMINAL_FAILURES:
                raise DeployRefused(f"{service} deployment {deployment.get('id')} ended {last_status}")
        if clock() >= deadline:
            raise DeployRefused(f"{service} deployment did not succeed within {int(timeout)}s (last: {last_status})")
        sleep(interval)


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        # /ready answers 503 with the same JSON shape; its revisions still count.
        body = exc.read()
    payload = json.loads(body.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def api_revision(payload: dict[str, Any]) -> str | None:
    return normalize_revision(payload.get("revision"))


def ready_revisions(payload: dict[str, Any]) -> dict[str, str | None]:
    revisions = payload.get("revision")
    if not isinstance(revisions, dict):
        return {"api": None, "worker": None}
    return {"api": normalize_revision(revisions.get("api")), "worker": normalize_revision(revisions.get("worker"))}


def served_revision(service: str, health_url: str, fetch: Callable[[str], dict[str, Any]]) -> str | None:
    if service == "api":
        return api_revision(fetch(f"{health_url}/health"))
    return ready_revisions(fetch(f"{health_url}/ready")).get(service)


def wait_for_revision(
    service: str,
    revision: str,
    health_url: str,
    *,
    fetch: Callable[[str], dict[str, Any]] = fetch_json,
    timeout: float = 300.0,
    interval: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout
    seen: str | None = None
    while True:
        try:
            seen = served_revision(service, health_url, fetch)
        except (OSError, ValueError):
            seen = None
        if seen == revision:
            return
        if clock() >= deadline:
            raise DeployRefused(
                f"{service} deployed but still reports revision {seen or 'unknown'} after {int(timeout)}s, "
                f"expected {revision[:12]}"
            )
        sleep(interval)


def linked_project(runner: Runner, repo: Path) -> str | None:
    result = runner(["railway", "status", "--json"], repo)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return None
    project = payload.get("id") if isinstance(payload, dict) else None
    return project if isinstance(project, str) and project else None


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0] if __doc__ else None)
    parser.add_argument("--ref", default=MAIN_REF, help="commit to deploy (default: origin/main after a fetch)")
    parser.add_argument("--project", help="Railway project ID (default: the one this checkout is linked to)")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--service", action="append", dest="services", help="repeatable; default: api then worker")
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--since", action="append", default=[], help="deployed commit to diff migrations against")
    parser.add_argument("--migrations-applied", action="store_true", help="migrations were run per the runbook")
    parser.add_argument("--skip-ci-check", action="store_true", help="deploy without a green ci.yml run (emergency)")
    parser.add_argument("--no-fetch", action="store_true", help="use the local origin/main without fetching")
    parser.add_argument("--timeout", type=float, default=1200.0, help="seconds to wait for each Railway build")
    parser.add_argument("--dry-run", action="store_true", help="check and export, but upload nothing")
    parser.add_argument("--keep-export", action="store_true", help="leave the exported tree on disk")
    return parser.parse_args(argv)


def _deployed_baselines(
    args: argparse.Namespace, services: Sequence[str], health_url: str, fetch: Callable[[str], dict[str, Any]]
) -> list[str | None]:
    if args.since:
        return [normalize_revision(value) or value for value in args.since]
    try:
        served = {
            "api": served_revision("api", health_url, fetch),
            "worker": served_revision("worker", health_url, fetch),
        }
    except (OSError, ValueError) as exc:
        raise DeployRefused(f"could not read the deployed revision from {health_url}: {exc}") from exc
    return [served.get(service) for service in services]


def deploy(
    args: argparse.Namespace,
    runner: Runner = run,
    repo: Path = ROOT,
    *,
    fetch: Callable[[str], dict[str, Any]] = fetch_json,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    services = tuple(args.services or DEFAULT_SERVICES)
    health_url = args.health_url.rstrip("/")
    if not args.no_fetch:
        _checked(runner, ["git", "fetch", "--quiet", "origin", "main"], repo)
    revision = resolve_revision(args.ref, runner, repo)
    ensure_on_main(revision, runner, repo)
    print(f"Revision: {revision} ({args.ref})")
    if args.skip_ci_check:
        print("CI: NOT CHECKED (--skip-ci-check)")
    else:
        check_ci(revision, runner, repo)
        print("CI: ci.yml succeeded for this exact commit")
    if args.migrations_applied:
        print("Migrations: confirmed applied by the operator")
    else:
        check_migrations(_deployed_baselines(args, services, health_url, fetch), revision, runner, repo)
        print("Migrations: none added since the deployed builds")

    project = args.project or linked_project(runner, repo)
    if not project:
        raise DeployRefused("no Railway project: pass --project or run from a checkout linked with `railway link`")
    target = Target(project, args.environment, services, health_url)

    workspace = Path(tempfile.mkdtemp(prefix="thoughtpins-deploy-"))
    export = workspace / "source"
    try:
        stamp = export_commit(revision, export, runner, repo, ref=args.ref)
        print(f"Export: {export} (stamped {stamp.relative_to(export).as_posix()})")
        if args.dry_run:
            for service in services:
                print(
                    "Would run:", " ".join(railway_up_command(target, service, deployment_message(revision, "<nonce>")))
                )
            return 0
        for service in services:
            nonce = uuid.uuid4().hex[:12]
            _checked(runner, railway_up_command(target, service, deployment_message(revision, nonce)), export)
            deployment_id = wait_for_deployment(target, service, nonce, runner, timeout=args.timeout, sleep=sleep)
            wait_for_revision(service, revision, target.health_url, fetch=fetch, sleep=sleep)
            print(f"{service}: deployment {deployment_id} is serving {revision}")
    finally:
        if args.keep_export:
            print(f"Kept export at {export}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)
    print(f"Production {', '.join(services)} now report {revision}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return deploy(args)
    except DeployRefused as exc:
        print(f"Deploy refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
