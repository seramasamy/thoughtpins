from __future__ import annotations

from pathlib import Path

import pytest

from scripts.web_assets import StylesheetBundleError, read_stylesheet_bundle


def test_stylesheet_bundle_preserves_nested_import_order(tmp_path: Path) -> None:
    styles = tmp_path / "styles"
    styles.mkdir()
    (styles / "tokens.css").write_text(":root { --brand: orange; }", encoding="utf-8")
    (styles / "view.css").write_text(
        '@import "./tokens.css";\n.view { color: var(--brand); }',
        encoding="utf-8",
    )
    entrypoint = tmp_path / "app.css"
    entrypoint.write_text('@import "./styles/view.css";\n.app { display: grid; }', encoding="utf-8")

    bundle = read_stylesheet_bundle(entrypoint)

    assert bundle.index(":root") < bundle.index(".view") < bundle.index(".app")


def test_stylesheet_bundle_rejects_import_cycles(tmp_path: Path) -> None:
    first = tmp_path / "first.css"
    second = tmp_path / "second.css"
    first.write_text('@import "./second.css";', encoding="utf-8")
    second.write_text('@import "./first.css";', encoding="utf-8")

    with pytest.raises(StylesheetBundleError, match="import cycle"):
        read_stylesheet_bundle(first)


def test_stylesheet_bundle_rejects_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.css").write_text("body {}", encoding="utf-8")
    entrypoint = root / "app.css"
    entrypoint.write_text('@import "../outside.css";', encoding="utf-8")

    with pytest.raises(StylesheetBundleError, match="escapes"):
        read_stylesheet_bundle(entrypoint)


def test_stylesheet_bundle_resolves_root_relative_asset_import(tmp_path: Path) -> None:
    assets = tmp_path / "site" / "assets"
    styles = assets / "styles"
    styles.mkdir(parents=True)
    (styles / "view.css").write_text(".view { display: grid; }", encoding="utf-8")
    entrypoint = assets / "styles.css"
    entrypoint.write_text('@import "/assets/styles/view.css";', encoding="utf-8")

    assert ".view { display: grid; }" in read_stylesheet_bundle(entrypoint)


def test_stylesheet_bundle_rejects_unknown_root_relative_import(tmp_path: Path) -> None:
    assets = tmp_path / "site" / "assets"
    assets.mkdir(parents=True)
    entrypoint = assets / "styles.css"
    entrypoint.write_text('@import "/private/view.css";', encoding="utf-8")

    with pytest.raises(StylesheetBundleError, match="unsupported root-relative"):
        read_stylesheet_bundle(entrypoint)
