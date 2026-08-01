from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.web_assets import read_stylesheet_bundle

ROOT = Path(__file__).resolve().parents[1]


def test_web_app_contract_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_web_app_contract.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Web app product contract check passed." in result.stdout


def test_web_app_contract_check_guards_deploy_bundle() -> None:
    checker = (ROOT / "scripts" / "check_web_app_contract.py").read_text(encoding="utf-8-sig")
    assert '(FRONTEND / "dist" / "assets").glob("*.js")' in checker
    assert 'FRONTEND / "dist" / "app.js"' in checker
    assert "no stale store readiness copy" in checker
    assert "Apple review expects useful app functionality beyond a repackaged website" in checker


def test_chat_confirmation_parser_is_exact(built_frontend) -> None:
    react_helper = (ROOT / "frontend/src/features/chat/confirmation.ts").read_text(encoding="utf-8-sig")
    react_chat = (ROOT / "frontend/src/features/chat/ChatView.tsx").read_text(encoding="utf-8-sig")
    static_app = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8-sig")
    dist_paths = sorted((ROOT / "frontend/dist/assets").glob("*.js"))
    if not dist_paths and (ROOT / "frontend/dist/app.js").is_file():
        dist_paths = [ROOT / "frontend/dist/app.js"]
    assert dist_paths, "production frontend JavaScript bundle is missing"
    dist_apps = [path.read_text(encoding="utf-8-sig") for path in dist_paths]

    for source in (react_helper, static_app):
        assert "GENERAL_CONFIRMATION_PHRASES" in source
        assert "CANCEL_CONFIRMATION_PHRASES" in source
        assert 'startsWith("confirm ")' not in source
        assert "^confirm|yes|do it$" not in source
    for source in dist_apps:
        assert 'startsWith("confirm ")' not in source
        assert "^confirm|yes|do it$" not in source

    assert "forceConfirm" in react_chat
    assert "Pending confirmation" in react_chat
    assert "Cancel" in react_chat
    assert "Confirm" in react_chat


def test_react_shell_keeps_cross_view_composer() -> None:
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8-sig")
    shell = (ROOT / "frontend/src/app/AppShell.tsx").read_text(encoding="utf-8-sig")
    styles = read_stylesheet_bundle(ROOT / "frontend/src/styles.css")

    assert "handleGlobalCompose" in app
    assert "api.chat(token" in app
    assert "api.ingest(token, body)" in app
    assert "onGlobalCompose={handleGlobalCompose}" in app
    assert "global-composer" in shell
    assert "Quick chat or journal composer" in shell
    assert 'showGlobalComposer = view !== "chat"' in shell
    assert "Ask Thought Pins..." in shell
    assert "Write a journal note" in shell
    assert ".app-shell.has-global-composer .main" in styles
    assert "bottom: calc(72px + env(safe-area-inset-bottom))" in styles
