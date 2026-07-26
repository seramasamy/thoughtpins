from __future__ import annotations

import pytest


def test_smoke_api_help_exits_before_network_work(capsys):
    from scripts import smoke_api

    with pytest.raises(SystemExit) as exc_info:
        smoke_api._parse_args(["--help"])

    assert exc_info.value.code == 0
    assert "disposable HTTP API smoke workflow" in capsys.readouterr().out


def test_smoke_api_boolean_flags_are_explicit():
    from scripts import smoke_api

    args = smoke_api._parse_args(
        ["--base-url", "https://example.test/", "--no-register", "--delete-account", "--wait-job"]
    )

    assert args.base_url == "https://example.test/"
    assert args.register is False
    assert args.delete_account is True
    assert args.wait_job is True
