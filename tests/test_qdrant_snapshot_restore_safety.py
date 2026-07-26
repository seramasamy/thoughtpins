from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_qdrant_snapshot_restore.py"


def test_qdrant_recovery_drill_rejects_application_collection_names() -> None:
    spec = importlib.util.spec_from_file_location("verify_qdrant_snapshot_restore", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    module.assert_safe_collection_name("thoughtpins_recovery_drill_012345abcdef")
    for name in [
        "journal_memories_1536",
        "thoughtpins_recovery_drill",
        "thoughtpins_recovery_drill_012345ABCDEf",
        "thoughtpins_recovery_drill_012345abcdef_extra",
    ]:
        try:
            module.assert_safe_collection_name(name)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe Qdrant recovery collection accepted: {name}")
