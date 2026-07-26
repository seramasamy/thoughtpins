from __future__ import annotations


def test_pwa_contract_passes() -> None:
    from scripts.check_pwa_contract import check_pwa_contract

    assert check_pwa_contract() == []
