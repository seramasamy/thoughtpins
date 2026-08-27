"""Offline App Store / Play Store readiness checks for Thought Pins.

This script checks engineering invariants that are easy to regress before native
store submission. It is not legal advice and does not replace App Store Connect
or Play Console forms.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.route_contracts import RouteDiscoveryError, discover_api_routes  # noqa: E402
from thoughtpins.config import config  # noqa: E402

POLICY_SOURCE_MAX_AGE_DAYS = 120
PUBLIC_UI_FOUNDER_COPY_MARKERS = (
    "Founder Telegram Test",
    "Founder mode",
    "Telegram test mode",
    "local founder",
    "local founder mode",
    "founder testing",
    "local founder testing",
)
REQUIRED_OFFICIAL_REFERENCES = {
    "apple_app_review_guidelines",
    "apple_app_privacy_details",
    "apple_account_deletion",
    "apple_user_privacy_and_data_use",
    "google_user_data_policy",
    "google_account_deletion",
    "google_data_safety_form",
    "google_ai_generated_content_policy",
}


def _public_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.hostname not in {"localhost", "127.0.0.1"}


def _contains(path: Path, needle: str) -> bool:
    return path.is_file() and needle in path.read_text(encoding="utf-8", errors="ignore")


def run_checks() -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    paths = _store_surface_paths()
    _check_required_files(paths, failures)
    if config.APP_NAME != "Thought Pins":
        failures.append("APP_NAME should be 'Thought Pins'.")
    _check_data_inventory(ROOT / "deploy" / "store" / "data-safety-inventory.json", failures)
    _check_public_routes(failures)
    _check_maintenance_contract(paths, failures)
    _check_oauth_parity(warnings, failures)
    _check_production_settings(warnings, failures)
    if _contains(ROOT / "frontend" / "package.json", "@capacitor"):
        warnings.append("Capacitor is installed. Ensure native submission is not just a thin web wrapper.")
    return failures, warnings


def _store_surface_paths() -> dict[str, Path]:
    return {
        "public route": ROOT / "src" / "thoughtpins" / "api_routes" / "public.py",
        "API route": ROOT / "src" / "thoughtpins" / "api.py",
        "metadata route": ROOT / "src" / "thoughtpins" / "api_routes" / "metadata.py",
        "static web app": ROOT / "frontend" / "static" / "app.js",
        "built web app": ROOT / "frontend" / "dist" / "app.js",
        "React app": ROOT / "frontend" / "src" / "App.tsx",
        "React shell": ROOT / "frontend" / "src" / "app" / "AppShell.tsx",
        "React account view": ROOT / "frontend" / "src" / "features" / "account" / "AccountView.tsx",
    }


def _check_required_files(paths: dict[str, Path], failures: list[str]) -> None:
    optional = {"built web app"}
    for label, path in paths.items():
        if label not in optional and not path.is_file():
            failures.append(f"Missing {label}: {path.relative_to(ROOT)}")


def _check_public_routes(failures: list[str]) -> None:
    try:
        routes = discover_api_routes(ROOT)
    except RouteDiscoveryError as exc:
        failures.append(str(exc))
        routes = set()
    if ("DELETE", "/v1/me") not in routes:
        failures.append("In-app account deletion endpoint /v1/me is missing.")

    # These pages are registered with include_in_schema=False, so they never
    # appear in the OpenAPI-derived route set above. Ask the router itself
    # rather than grepping for a decorator: the reviewer-facing requirement is
    # that the path answers, not that it was spelled a particular way.
    from thoughtpins.api_routes.public import create_public_router

    published = {getattr(route, "path", "") for route in create_public_router().routes}
    for path, label in (
        ("/account/delete", "Public web account deletion page"),
        ("/privacy", "Public privacy page"),
        ("/ai-disclosure", "Public AI disclosure page"),
    ):
        if path not in published:
            failures.append(f"{label} is missing.")
        # A store reviewer or crawler that appends a slash must not be handed
        # the authenticated catch-all instead of the policy.
        elif f"{path}/" not in published:
            failures.append(f"{label} does not answer its trailing-slash form.")


def _check_maintenance_contract(paths: dict[str, Path], failures: list[str]) -> None:
    # The request middleware is split between api.py and api_gateway.py, so the
    # maintenance refusal can live in either. The claim being checked is that
    # the API exposes a structured maintenance_mode error, not which module
    # holds the literal.
    middleware = [paths["API route"], ROOT / "src" / "thoughtpins" / "api_gateway.py"]
    if not any(_contains(candidate, '"maintenance_mode"') for candidate in middleware):
        failures.append("API does not expose a structured maintenance_mode error.")
    if not _contains(paths["metadata route"], "maintenance_mode"):
        failures.append("Client config does not expose maintenance_mode.")
    for private_flag in ("telegram_enabled", "telegram_test_mode", "founder_test_mode_enabled"):
        if _contains(paths["metadata route"], private_flag):
            failures.append(f"Client config must not expose private adapter flag: {private_flag}")
    if not _contains(paths["static web app"], "renderMaintenanceBanner"):
        failures.append("Static fallback web app does not render a maintenance banner.")
    if not _contains(paths["React app"], "maintenanceMessage"):
        failures.append("React web app does not wire maintenanceMessage.")
    _check_public_ui_no_founder_copy(list(paths.values()), failures)
    if config.MAINTENANCE_RETRY_AFTER_SECONDS < 0:
        failures.append("MAINTENANCE_RETRY_AFTER_SECONDS cannot be negative.")
    if not config.MAINTENANCE_MESSAGE.strip():
        failures.append("MAINTENANCE_MESSAGE must not be empty.")


def _check_oauth_parity(warnings: list[str], failures: list[str]) -> None:
    if config.GOOGLE_OAUTH_CLIENT_IDS and not config.APPLE_OAUTH_CLIENT_IDS:
        warnings.append(
            "Google OAuth is configured without Apple OAuth. If third-party login is offered on iOS, enable Sign in with Apple."
        )
    if config.APPLE_OAUTH_CLIENT_IDS and not _contains(ROOT / "src" / "thoughtpins" / "oauth.py", "appleid.apple.com"):
        failures.append("Apple OAuth client IDs are configured but Apple verifier metadata is missing.")


def _check_production_settings(warnings: list[str], failures: list[str]) -> None:
    if not config.is_production():
        return
    if not config.REQUIRE_API_AUTH:
        failures.append("Production must require API auth.")
    if config.SYSTEM_LOCKED and not (config.ALLOW_OAUTH_REGISTRATION or not config.RETURN_API_KEY_ON_REGISTER):
        warnings.append("SYSTEM_LOCKED is enabled; confirm this is intentional for public signup.")
    if config.ENABLE_FOUNDER_MODE or config.TELEGRAM_TEST_MODE:
        failures.append("Founder/Telegram test mode must be disabled in production store builds.")
    required_urls = {
        "PRIVACY_POLICY_URL": config.PRIVACY_POLICY_URL,
        "TERMS_URL": config.TERMS_URL,
        "ACCOUNT_DELETION_URL": config.ACCOUNT_DELETION_URL,
        "AI_DISCLOSURE_URL": config.AI_DISCLOSURE_URL,
    }
    for name, value in required_urls.items():
        if not _public_https(value):
            failures.append(f"{name} must be a public HTTPS URL for store submission.")
    if not (_public_https(config.SUPPORT_URL) or config.SUPPORT_URL.startswith("mailto:")):
        failures.append("SUPPORT_URL must be public HTTPS or mailto for store submission.")
    if not config.SENTRY_DSN:
        warnings.append(
            "SENTRY_DSN is not set. Store submission can pass without it, but crash visibility will be weak."
        )


def _check_public_ui_no_founder_copy(paths: list[Path], failures: list[str]) -> None:
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        lowered = text.lower()
        for marker in PUBLIC_UI_FOUNDER_COPY_MARKERS:
            if marker.lower() in lowered:
                failures.append(f"{path.relative_to(ROOT)} exposes founder/test-only copy in public UI: {marker!r}")


def _check_data_inventory(path: Path, failures: list[str]) -> None:
    if not path.is_file():
        failures.append("Store data-safety inventory is missing: deploy/store/data-safety-inventory.json")
        return
    try:
        inventory = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"Store data-safety inventory is invalid JSON: {exc}")
        return

    if inventory.get("app_name") != "Thought Pins":
        failures.append("Store data-safety inventory must identify Thought Pins.")
    if inventory.get("tracking", {}).get("used_for_tracking") is not False:
        failures.append("Store data-safety inventory must explicitly declare no tracking for v1.")
    if inventory.get("ai_processing", {}).get("disclosure_required") is not True:
        failures.append("Store data-safety inventory must require AI disclosure.")
    if inventory.get("account_deletion", {}).get("api_endpoint") != "DELETE /v1/me":
        failures.append("Store data-safety inventory must map account deletion to DELETE /v1/me.")
    ai_safety = inventory.get("ai_safety", {})
    if ai_safety.get("unsafe_output_reporting") is not True:
        failures.append("Store data-safety inventory must document unsafe AI output reporting.")
    if ai_safety.get("reporting_channel") != "support@thoughtpins.com":
        failures.append("Store data-safety inventory must map AI safety reports to support@thoughtpins.com.")
    if ai_safety.get("in_app_reporting") is not True:
        failures.append("Store data-safety inventory must document in-app safety reporting.")
    if ai_safety.get("report_endpoint") != "POST /v1/safety/reports":
        failures.append("Store data-safety inventory must map safety reports to POST /v1/safety/reports.")
    ugc = inventory.get("user_generated_content", {})
    if ugc.get("private_by_default") is not True or ugc.get("public_posting") is not False:
        failures.append("Store data-safety inventory must document private-by-default user content.")
    if ugc.get("report_endpoint") != "POST /v1/safety/reports":
        failures.append("Store data-safety inventory must map user-content reports to POST /v1/safety/reports.")
    source_policy = inventory.get("copyright_and_sources", {})
    if source_policy.get("access_control_circumvention") is not False:
        failures.append("Store data-safety inventory must prohibit access-control circumvention.")
    if source_policy.get("user_submitted_sources_only") is not True:
        failures.append("Store data-safety inventory must limit imports to user-submitted sources.")

    category_names = {str(item.get("store_category", "")).lower() for item in inventory.get("data_categories", [])}
    for required in {"contact info", "user content", "identifiers", "diagnostics"}:
        if required not in category_names:
            failures.append(f"Store data-safety inventory missing category: {required}")

    _check_policy_date("Store data-safety inventory last_reviewed", inventory.get("last_reviewed"), failures)

    references = inventory.get("official_references", {})
    for key in REQUIRED_OFFICIAL_REFERENCES:
        value = references.get(key, "")
        if not isinstance(value, str) or not value.startswith("https://"):
            failures.append(f"Store data-safety inventory missing official reference: {key}")


def _check_policy_date(label: str, value: object, failures: list[str], *, today: date | None = None) -> None:
    today = today or date.today()
    if not isinstance(value, str) or not value.strip():
        failures.append(f"{label} must be an ISO date")
        return
    try:
        checked_on = date.fromisoformat(value)
    except ValueError:
        failures.append(f"{label} must be an ISO date, got {value!r}")
        return
    if checked_on > today:
        failures.append(f"{label} cannot be in the future")
        return
    age_days = (today - checked_on).days
    if age_days > POLICY_SOURCE_MAX_AGE_DAYS:
        failures.append(f"{label} is stale ({age_days} days old); refresh official Apple/Google policy review")


def main() -> int:
    failures, warnings = run_checks()
    for warning in warnings:
        print(f"WARN: {warning}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"App store compliance check failed: {len(failures)} failure(s), {len(warnings)} warning(s).")
        return 1
    print(f"App store compliance check passed with {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
