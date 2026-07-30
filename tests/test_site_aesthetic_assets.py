from __future__ import annotations

import re
from pathlib import Path

from scripts.web_assets import read_stylesheet_bundle

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_declares_social_touch_and_product_visual_assets():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assets = ROOT / "site" / "assets"

    assert "data-product-demo" in html
    assert 'data-preview-tab="desktop"' in html
    assert 'data-preview-tab="mobile"' in html
    assert "Illustrative preview." in html
    assert 'property="og:image" content="https://thoughtpins.com/assets/product-chat-desktop.png"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    # Assert the icon is cache-busted, not which version it is pinned to.
    # Freezing the exact string made every legitimate cache bump a test failure.
    assert re.search(
        r'rel="apple-touch-icon" href="/assets/apple-touch-icon\.png\?v=[A-Za-z0-9._-]+"',
        html,
    ), "apple-touch-icon must be referenced with a cache-busting ?v= query"
    assert (assets / "product-chat-desktop.png").stat().st_size > 20_000
    touch_icon = (assets / "apple-touch-icon.png").read_bytes()
    assert touch_icon.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(touch_icon[16:20], "big") == 1024
    assert int.from_bytes(touch_icon[20:24], "big") == 1024


def test_homepage_hero_uses_matte_surface_without_decorative_glow():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    css = read_stylesheet_bundle(ROOT / "site" / "assets" / "styles.css")
    hero_block = css.split(".hero {", 1)[1].split("}", 1)[0]

    assert "hero-glow" not in html
    assert ".hero-glow" not in css
    assert 'url("/assets/product-chat-desktop.png")' not in hero_block
    assert "background: #2b241d" in hero_block
    assert "gradient" not in hero_block
    assert ".hero::before" in css
