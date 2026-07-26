"""Run pytest with a Windows sandbox compatibility shim.

Some local Windows sandboxes treat directories created with Python's 0o700 mode
as unreadable, even to the creating process. Pytest and tempfile use that mode
for scratch directories, which can make otherwise valid tests fail during
tmp_path setup or cleanup. The shim only relaxes that directory mode on Windows
before importing pytest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def _patch_windows_private_dirs() -> None:
    if os.name != "nt":
        return

    original_mkdir = os.mkdir

    def mkdir(path, mode=0o777, *args, **kwargs):
        if mode == 0o700:
            mode = 0o777
        return original_mkdir(path, mode, *args, **kwargs)

    os.mkdir = mkdir


def main() -> int:
    _patch_windows_private_dirs()
    root_path = str(ROOT)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    if os.name == "nt":
        temp_root = ROOT / ".tmp" / "pytest-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        os.environ["TMP"] = str(temp_root)
        os.environ["TEMP"] = str(temp_root)
        if not any(arg == "--basetemp" or arg.startswith("--basetemp=") for arg in sys.argv[1:]):
            sys.argv.extend(["--basetemp", str(ROOT / ".tmp" / f"pytest-run-{uuid4().hex}")])
    import pytest

    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
