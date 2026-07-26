"""Build and verify a sanitized source archive from the public allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import check_public_export

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "PUBLIC_EXPORT_MANIFEST.json"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-export" / "ThoughtPins-public-source.zip",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing archive.")
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists() and not args.force:
        print(f"Public export failed: output already exists: {output}")
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)

    checked = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_public_export.py")],
        cwd=ROOT,
        check=False,
    )
    if checked.returncode != 0:
        print("Public export failed: source hygiene check did not pass")
        return 1

    manifest = check_public_export.build_public_export_manifest(ROOT)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        print("Public export failed: manifest contains no files")
        return 1

    try:
        _write_archive(output, files, manifest)
        _verify_archive(output, files)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        output.unlink(missing_ok=True)
        print(f"Public export failed: {exc}")
        return 1

    size = output.stat().st_size
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"Public export created: {output}")
    print(f"Files: {len(files)} | Bytes: {size} | SHA-256: {digest}")
    return 0


def _write_archive(output: Path, files: list[object], manifest: dict[str, object]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("manifest contains an invalid file record")
            relative = str(item["path"])
            source = ROOT / relative
            _write_bytes(archive, relative, source.read_bytes())
        _write_bytes(
            archive,
            MANIFEST_NAME,
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )


def _write_bytes(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content, compresslevel=9)


def _verify_archive(output: Path, files: list[object]) -> None:
    expected = {
        str(item["path"]): str(item["sha256"])
        for item in files
        if isinstance(item, dict) and "path" in item and "sha256" in item
    }
    with zipfile.ZipFile(output, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("archive contains duplicate paths")
        if set(names) != {*expected, MANIFEST_NAME}:
            raise ValueError("archive paths do not match the checked public manifest")
        for name, expected_hash in expected.items():
            actual_hash = hashlib.sha256(archive.read(name)).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(f"archive hash mismatch: {name}")
        embedded = json.loads(archive.read(MANIFEST_NAME))
        if embedded.get("file_count") != len(expected):
            raise ValueError("embedded manifest file count does not match archive")


if __name__ == "__main__":
    raise SystemExit(main())
