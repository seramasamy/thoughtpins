from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_export_check_passes_current_tree() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_public_export.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Public export check passed" in result.stdout


def test_public_export_ignores_generated_local_state(tmp_path: Path) -> None:
    mod = _load_script("check_public_export")
    for dirname in ["pytest-basetemp", "pytest-cache-files-example", "tmp-test-write-check", "write_probe_abc123"]:
        path = tmp_path / dirname
        path.mkdir()
        (path / "secret.txt").write_text(
            "sk-" + "proj-" + "thisshouldnotbescannedbecauseitislocalstate123456", encoding="utf-8"
        )
    package_metadata = tmp_path / "src" / "thoughtpins.egg-info"
    package_metadata.mkdir(parents=True)
    (package_metadata / "SOURCES.txt").write_text("stale generated package metadata", encoding="utf-8")

    files = list(mod._candidate_files(tmp_path))
    assert files == []


def test_forbidden_scan_ignores_generated_local_state_and_catches_provider_keys(tmp_path: Path) -> None:
    mod = _load_script("forbidden_scan")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "safe.py").write_text('NAME = "Thought Pins"\n', encoding="utf-8")
    for dirname in ["pytest-basetemp", "pytest-cache-files-example", "tmp-test-write-check", "write_probe_abc123"]:
        path = tmp_path / dirname
        path.mkdir()
        (path / "local.txt").write_text("jina_" + "thislocalvalueisnotpartofthepublictree", encoding="utf-8")
    package_metadata = tmp_path / "src" / "thoughtpins.egg-info"
    package_metadata.mkdir()
    (package_metadata / "SOURCES.txt").write_text(
        "jina_" + "thisgeneratedvalueisnotpartofthepublictree",
        encoding="utf-8",
    )

    assert mod.main(tmp_path) == 0

    (tmp_path / "src" / "bad.py").write_text(
        "TOKEN = '" + "fc-" + "1234567890abcdef1234567890abcdef" + "'\n", encoding="utf-8"
    )
    assert mod.main(tmp_path) == 1

    (tmp_path / "src" / "bad.py").write_text("provider = '" + "deep" + "seek" + "'\n", encoding="utf-8")
    assert mod.main(tmp_path) == 1


def test_public_export_manifest_uses_relative_safe_paths(tmp_path: Path) -> None:
    manifest_path = tmp_path / "public-export-manifest.json"
    result = subprocess.run(
        [sys.executable, "scripts/check_public_export.py", "--write-manifest", str(manifest_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [entry["path"] for entry in manifest["files"]]

    assert manifest["app"] == "Thought Pins"
    assert manifest["schema_version"] == 1
    assert manifest["file_count"] == len(paths)
    assert "README.md" in paths
    assert "founder/README.md" in paths
    assert "founder/TELEGRAM_RUNBOOK.md" in paths
    assert "scripts/check_public_export.py" in paths
    assert "scripts/forbidden_scan.py" in paths
    assert "frontend/public/assets/thought-pins-icon-1024.png" in paths
    assert "mobile/ios/ThoughtPinsNative/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png" in paths
    assert all(isinstance(path, str) for path in paths)
    assert all(not Path(path).is_absolute() for path in paths)
    assert all("\\" not in path for path in paths)
    assert all("c:/users" not in path.lower() and "c:\\users" not in path.lower() for path in paths)
    assert all(not path.startswith(("reports/", "vault/", "data/", "founder/private/")) for path in paths)
    assert all(".egg-info/" not in path for path in paths)


def test_public_export_and_forbidden_scanners_scan_themselves() -> None:
    public_mod = _load_script("check_public_export")
    public_paths = {path.relative_to(ROOT).as_posix() for path in public_mod._candidate_files(ROOT)}
    assert "scripts/check_public_export.py" in public_paths
    assert "scripts/forbidden_scan.py" in public_paths

    forbidden_mod = _load_script("forbidden_scan")
    forbidden_paths = {path.relative_to(ROOT).as_posix() for path in forbidden_mod.iter_files(ROOT)}
    assert "scripts/check_public_export.py" in forbidden_paths
    assert "scripts/forbidden_scan.py" in forbidden_paths


def test_founder_public_surface_is_allowlisted_and_private_is_skipped(tmp_path: Path) -> None:
    mod = _load_script("check_public_export")
    founder = tmp_path / "founder"
    private = founder / "private"
    private.mkdir(parents=True)
    (founder / "README.md").write_text("# Founder Local Mode\n", encoding="utf-8")
    (founder / "TELEGRAM_RUNBOOK.md").write_text("# Founder Telegram Runbook\n", encoding="utf-8")
    (founder / "notes.md").write_text("local-only scratch notes\n", encoding="utf-8")
    (private / "secret.txt").write_text("sk-" + "localprivatevalueisnotpublicexportcontent123", encoding="utf-8")

    findings: list[str] = []
    mod._check_founder_public_surface(tmp_path, findings)
    manifest = mod.build_public_export_manifest(tmp_path)
    paths = [entry["path"] for entry in manifest["files"]]

    assert any("founder/notes.md" in finding for finding in findings)
    assert all("founder/private" not in finding for finding in findings)
    assert "founder/private/secret.txt" not in paths
    assert "founder/README.md" in paths
    assert "founder/TELEGRAM_RUNBOOK.md" in paths


def test_public_export_only_includes_binary_images_from_product_asset_roots(tmp_path: Path) -> None:
    mod = _load_script("check_public_export")
    approved = tmp_path / "site" / "assets"
    unapproved = tmp_path / "docs"
    approved.mkdir(parents=True)
    unapproved.mkdir()
    (approved / "brand.png").write_bytes(b"safe-product-asset")
    (unapproved / "private-screenshot.png").write_bytes(b"not-for-export")

    paths = {path.relative_to(tmp_path).as_posix() for path in mod._candidate_files(tmp_path)}

    assert "site/assets/brand.png" in paths
    assert "docs/private-screenshot.png" not in paths
