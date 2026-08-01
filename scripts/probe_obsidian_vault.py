"""Probe whether an exported vault can be handed to a local Obsidian install."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thoughtpins.vault.validator import validate_vault  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally open a vault in local Obsidian.")
    parser.add_argument("vault", type=Path, help="Vault folder to probe")
    parser.add_argument("--open", action="store_true", help="Attempt to launch Obsidian with the vault folder")
    parser.add_argument("--cli", action="store_true", help="Run read/search/diagnostic checks through Obsidian CLI")
    parser.add_argument(
        "--require-cli", action="store_true", help="Fail when requested CLI acceptance checks are unavailable"
    )
    parser.add_argument("--cli-vault-name", help="Obsidian vault name used by CLI; defaults to the folder name")
    parser.add_argument("--cli-screenshot", type=Path, help="Optional path for an Obsidian CLI developer screenshot")
    parser.add_argument(
        "--wait-seconds", type=float, default=3.0, help="Wait after launch before inspecting vault-local config"
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    vault = args.vault.resolve()
    validation = validate_vault(vault)
    obsidian = _find_obsidian_executable()
    protocol_handler = _find_obsidian_protocol_handler()
    cli = shutil.which("obsidian")
    payload: dict[str, object] = {
        "vault": str(vault),
        "validation_ok": validation.ok,
        "validation_errors": [finding.__dict__ for finding in validation.errors],
        "obsidian_executable": str(obsidian) if obsidian else None,
        "obsidian_protocol_handler": protocol_handler,
        "obsidian_cli_executable": cli,
        "obsidian_cli": {"requested": args.cli, "available": bool(cli), "ok": None, "checks": []},
        "obsidian_processes_before": _obsidian_processes(),
        "obsidian_processes_after": [],
        "load_attempted": False,
        "load_result": "not_attempted",
        "open_uri": _obsidian_uri(vault),
        "obsidian_config": _inspect_obsidian_config(vault),
    }

    if args.open:
        if not validation.ok:
            payload["load_result"] = "blocked_by_validation_errors"
        elif obsidian:
            payload["load_attempted"] = True
            try:
                subprocess.Popen(
                    [str(obsidian), _obsidian_uri(vault)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                payload["load_result"] = "launched_obsidian_uri"
            except Exception as exc:
                payload["load_result"] = f"launch_failed: {exc}"
        elif protocol_handler and sys.platform == "win32":
            payload["load_attempted"] = True
            try:
                os.startfile(_obsidian_uri(vault))
                payload["load_result"] = "launched_obsidian_protocol"
            except Exception as exc:
                payload["load_result"] = f"protocol_launch_failed: {exc}"
        else:
            payload["load_result"] = "obsidian_not_installed_or_not_found"

        if payload.get("load_attempted"):
            time.sleep(max(0.0, args.wait_seconds))
            payload["obsidian_processes_after"] = _obsidian_processes()
            payload["obsidian_config"] = _inspect_obsidian_config(vault)

    if args.cli:
        if cli:
            payload["obsidian_cli"] = _run_obsidian_cli(
                cli,
                vault_name=args.cli_vault_name or vault.name,
                screenshot=args.cli_screenshot,
            )
        else:
            payload["obsidian_cli"] = {
                "requested": True,
                "available": False,
                "ok": False,
                "checks": [],
                "reason": "obsidian command is not available on PATH",
            }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Vault: {payload['vault']}")
        print(f"Validator OK: {payload['validation_ok']}")
        print(f"Obsidian executable: {payload['obsidian_executable'] or 'not found'}")
        print(f"Obsidian protocol: {payload['obsidian_protocol_handler'] or 'not found'}")
        print(f"Obsidian CLI: {payload['obsidian_cli_executable'] or 'not found'}")
        print(f"Open URI: {payload['open_uri']}")
        print(f"Load result: {payload['load_result']}")
        config = payload["obsidian_config"]
        if isinstance(config, dict):
            print(f".obsidian exists: {config.get('exists')}")
            print(f".obsidian JSON valid: {config.get('json_valid')}")
    cli_result = payload.get("obsidian_cli")
    cli_ok = isinstance(cli_result, dict) and cli_result.get("ok") is True
    if args.require_cli and not cli_ok:
        return 2
    return 0 if validation.ok else 1


def _run_obsidian_cli(executable: str, *, vault_name: str, screenshot: Path | None) -> dict[str, object]:
    """Run read-only Obsidian CLI acceptance checks without managing GUI processes."""
    commands: list[tuple[str, list[str]]] = [
        ("help", ["help"]),
        ("read_home", [f"vault={vault_name}", "read", "path=Vault Home.md"]),
        ("search", [f"vault={vault_name}", "search", "query=Thought Pins", "limit=5", "total"]),
        ("properties", [f"vault={vault_name}", "properties", "path=Vault Home.md"]),
        (
            "base_query",
            [
                f"vault={vault_name}",
                "base:query",
                "path=_Views/Journal.base",
                "view=Recent entries",
                "format=json",
            ],
        ),
        ("unresolved_links", [f"vault={vault_name}", "unresolved", "total"]),
        ("developer_errors", [f"vault={vault_name}", "dev:errors"]),
    ]
    if screenshot is not None:
        target = screenshot.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        commands.append(("screenshot", [f"vault={vault_name}", "dev:screenshot", f"path={target}"]))

    checks: list[dict[str, object]] = []
    for name, arguments in commands:
        try:
            completed = subprocess.run(
                [executable, *arguments],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=30,
            )
            checks.append(
                {
                    "name": name,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip()[:4_000],
                    "stderr": completed.stderr.strip()[:2_000],
                    "ok": completed.returncode == 0,
                }
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({"name": name, "returncode": None, "stdout": "", "stderr": str(exc), "ok": False})
    return {
        "requested": True,
        "available": True,
        "ok": bool(checks) and all(check.get("ok") is True for check in checks),
        "vault_name": vault_name,
        "checks": checks,
    }


def _find_obsidian_executable() -> Path | None:
    candidates: list[Path] = []
    local_app_data = os.getenv("LOCALAPPDATA")
    program_files = os.getenv("ProgramFiles")
    program_files_x86 = os.getenv("ProgramFiles(x86)")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Obsidian" / "Obsidian.exe")
        candidates.append(Path(local_app_data) / "Programs" / "Obsidian" / "Obsidian.exe")
    if program_files:
        candidates.append(Path(program_files) / "Obsidian" / "Obsidian.exe")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "Obsidian" / "Obsidian.exe")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _find_obsidian_protocol_handler() -> str | None:
    # Written as a positive sys.platform test because that is the form static
    # checkers treat as a platform guard: an early return leaves the Windows-only
    # body looking like dead code when the check runs on Linux.
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"obsidian\shell\open\command") as key:
                value, _ = winreg.QueryValueEx(key, "")
                return str(value)
        except Exception:
            return None
    else:
        return None


def _obsidian_uri(vault: Path) -> str:
    return "obsidian://open?path=" + quote(str(vault), safe="")


def _inspect_obsidian_config(vault: Path) -> dict[str, object]:
    config_dir = vault / ".obsidian"
    payload: dict[str, object] = {
        "exists": config_dir.exists(),
        "files": [],
        "json_valid": True,
        "json_errors": [],
        "community_plugins_present": False,
    }
    if not config_dir.exists():
        return payload
    files: list[str] = []
    json_errors: list[str] = []
    for path in sorted(config_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(vault).as_posix()
        files.append(rel)
        if path.name in {"community-plugins.json", "plugins.json"}:
            payload["community_plugins_present"] = True
        if path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8") or "{}")
            except Exception as exc:
                json_errors.append(f"{rel}: {exc}")
    payload["files"] = files
    payload["json_valid"] = not json_errors
    payload["json_errors"] = json_errors
    return payload


def _obsidian_processes() -> list[dict[str, str]]:
    # Positive platform test so the Windows-only body is not read as dead
    # code by a static check running on Linux.
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name Obsidian -ErrorAction SilentlyContinue | "
            "Select-Object Id,ProcessName,Path | ConvertTo-Json -Compress",
        ]
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=10)
        except Exception:
            return []
        text = completed.stdout.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []
        rows: list[dict[str, str]] = []
        for item in payload:
            if isinstance(item, dict):
                rows.append({key: str(value) for key, value in item.items() if value is not None})
        return rows
    else:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
