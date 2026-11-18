"""The npm audit gate stays strict and lets only a reviewed, unexpired advisory through."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location("check_npm_audit", ROOT / "scripts" / "check_npm_audit.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _advisory(ghsa: str, name: str, severity: str = "high") -> dict:
    return {
        "source": 1,
        "name": name,
        "severity": severity,
        "url": f"https://github.com/advisories/{ghsa}",
        "title": "t",
    }


AUDIT = {
    "vulnerabilities": {
        "picomatch": {"severity": "high", "via": [_advisory("GHSA-aaaa-bbbb-cccc", "picomatch")]},
        "fdir": {"severity": "high", "via": ["picomatch"]},
        "vite": {"severity": "high", "via": ["picomatch", "fdir"]},
        "minor-lib": {"severity": "moderate", "via": [_advisory("GHSA-mod0-mod0-mod0", "minor-lib", "moderate")]},
    }
}


def _exception(
    advisory: str = "GHSA-aaaa-bbbb-cccc", reviewed: str = "2026-11-17", expires: str = "2026-12-17"
) -> dict:
    return {
        "advisory": advisory,
        "package": "picomatch",
        "reason": "build-time only, no fix",
        "reviewed_on": reviewed,
        "expires_on": expires,
    }


def test_an_unexcepted_high_advisory_fails_and_moderate_ones_do_not() -> None:
    failures, _ = _checker().evaluate(AUDIT, [], date(2026, 11, 17))
    assert failures == ["GHSA-aaaa-bbbb-cccc (picomatch) is high or critical and not excepted"]


def test_a_reviewed_exception_excuses_only_its_own_advisory() -> None:
    mod = _checker()
    failures, notes = mod.evaluate(AUDIT, [_exception()], date(2026, 11, 20))
    assert failures == []
    assert any("excepted until 2026-12-17" in note for note in notes)

    audit = json.loads(json.dumps(AUDIT))
    audit["vulnerabilities"]["picomatch"]["via"].append(_advisory("GHSA-new0-new0-new0", "picomatch", "critical"))
    failures, _ = mod.evaluate(audit, [_exception()], date(2026, 11, 20))
    assert failures == ["GHSA-new0-new0-new0 (picomatch) is high or critical and not excepted"]


def test_an_expired_or_overlong_exception_fails() -> None:
    mod = _checker()
    failures, _ = mod.evaluate(AUDIT, [_exception()], date(2026, 12, 18))
    assert any("expired on 2026-12-17" in failure for failure in failures)
    assert any("GHSA-aaaa-bbbb-cccc (picomatch) is high or critical and not excepted" in f for f in failures)

    failures, _ = mod.evaluate(AUDIT, [_exception(expires="2027-02-01")], date(2026, 11, 20))
    assert any("lasts more than 31 days" in failure for failure in failures)


def test_incomplete_or_stale_entries_are_reported() -> None:
    mod = _checker()
    failures, _ = mod.evaluate(AUDIT, [{"advisory": "GHSA-aaaa-bbbb-cccc", "package": "picomatch"}], date(2026, 11, 20))
    assert any("missing reason" in failure for failure in failures)

    failures, notes = mod.evaluate({"vulnerabilities": {}}, [_exception()], date(2026, 11, 20))
    assert failures == []
    assert any("no longer matches any advisory; remove it" in note for note in notes)


def test_the_cli_reads_a_saved_report(tmp_path: Path) -> None:
    mod = _checker()
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({"vulnerabilities": {}}), encoding="utf-8")
    assert mod.main(["--audit-json", str(report)]) == 0


def test_the_committed_exceptions_are_well_formed_and_time_boxed() -> None:
    data = json.loads((ROOT / "deploy" / "security" / "npm-audit-exceptions.json").read_text(encoding="utf-8"))
    for entry in data["exceptions"]:
        assert _checker()._entry_problem(entry) is None
        reviewed = date.fromisoformat(entry["reviewed_on"])
        expires = date.fromisoformat(entry["expires_on"])
        assert 0 < (expires - reviewed).days <= 31
