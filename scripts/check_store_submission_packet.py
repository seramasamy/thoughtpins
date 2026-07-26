"""Validate the Thought Pins store-submission packet.

This is an offline consistency check. It does not submit anything to Apple or
Google; it verifies that the repo contains a coherent, non-secret packet for
closed-beta store review prep.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.route_contracts import RouteDiscoveryError, discover_api_routes  # noqa: E402

PACKET = ROOT / "deploy" / "store" / "submission-packet.json"
INVENTORY = ROOT / "deploy" / "store" / "data-safety-inventory.json"
POLICY_REQUIREMENTS = ROOT / "deploy" / "store" / "store-policy-requirements.json"
REVIEW_NOTES = ROOT / "deploy" / "store" / "review-notes-template.md"
DEPLOYMENT_PACKET = ROOT / "deploy" / "closed-beta-deployment-packet.json"
POLICY_SOURCE_MAX_AGE_DAYS = 120

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

REQUIRED_PUBLIC_URLS = {
    "marketing_site": "https://thoughtpins.com",
    "privacy_policy": "https://thoughtpins.com/privacy",
    "terms": "https://thoughtpins.com/terms",
    "support": "https://thoughtpins.com/support",
    "account_deletion": "https://thoughtpins.com/account/delete",
    "ai_disclosure": "https://thoughtpins.com/ai-disclosure",
    "web_app": "https://app.thoughtpins.com/app",
    "api": "https://api.thoughtpins.com/v1",
}

REQUIRED_SITE_MARKERS = {
    "site/privacy.html": [
        "Privacy Policy",
        "Data categories",
        "Contact Info",
        "User Content",
        "Journal and document content may be sent to configured third-party AI providers",
        "Thought Pins does not use journal content for advertising or cross-app tracking",
        "Users can export account data",
        "support@thoughtpins.com",
        "third-party AI providers",
        "explicit permission",
        "does not defeat publisher controls",
    ],
    "site/account/delete/index.html": [
        "Delete Account",
        "delete their account and associated data",
        "Web deletion request",
        "request account deletion and associated data deletion",
        "What deletion removes",
        "Exports before deletion",
        "within 30 days",
        "support@thoughtpins.com",
    ],
    "site/ai-disclosure.html": [
        "AI Disclosure",
        "journal",
        "AI",
        "Human control",
        "Provider-neutral runtime",
        "No professional advice",
        "Safety and reporting",
        "unsafe AI output",
        "harmful or illegal content",
    ],
    "site/support.html": [
        "Support",
        "account deletion",
        "privacy",
        "AI safety reports",
        "unsafe AI output",
    ],
    "site/terms.html": [
        "Terms",
        "Thought Pins",
        "copyrighted articles",
        "defeat publisher, account, or license controls",
    ],
}

REQUIRED_APPLE_GATES = {
    "complete_metadata_and_functional_urls",
    "demo_account_or_demo_mode",
    "backend_live_during_review",
    "in_app_account_deletion",
    "privacy_details_match_runtime",
    "sign_in_with_apple_parity",
    "no_hidden_founder_features",
    "ai_disclosure_and_safety_reporting",
    "user_generated_content_safety_controls",
}
REQUIRED_GOOGLE_GATES = {
    "privacy_policy_public_url",
    "data_safety_form",
    "in_app_account_deletion",
    "web_account_deletion_resource",
    "secure_handling_and_no_sale",
    "runtime_permissions_disclosed_before_use",
    "ai_generated_content_safety",
}

REQUIRED_COMMANDS = {
    "python scripts/release_check.py --skip-quality",
    "python scripts/collect_local_closed_beta_evidence.py --telegram-api --live-article --web-smoke",
    "python scripts/smoke_startup_shutdown.py",
    "python scripts/check_store_submission_packet.py",
    "python scripts/check_store_readiness_matrix.py --self-test",
    "python scripts/generate_store_readiness_matrix.py",
    "python scripts/check_deployment_packet.py",
    "python scripts/check_launch_packet.py",
    "python scripts/check_host_capabilities.py",
    "python scripts/check_native_review_handoff.py",
    "python scripts/check_review_notes_packet.py",
    "python scripts/check_review_account_packet.py",
    "python scripts/app_store_compliance_check.py",
    "python scripts/check_domain_readiness.py",
    "python scripts/check_public_export.py",
    "python scripts/collect_closed_beta_evidence.py --web-smoke",
}

REQUIRED_POLICY_IDS = {
    "apple_review_access",
    "apple_live_backend",
    "apple_privacy_policy_and_retention",
    "apple_in_app_account_deletion",
    "apple_sign_in_with_apple_parity",
    "google_privacy_policy",
    "google_data_safety",
    "google_in_app_account_deletion",
    "google_web_account_deletion",
    "google_secure_handling_and_no_sale",
    "public_build_no_founder_leakage",
    "apple_ai_disclosure_and_safety_reporting",
    "apple_user_generated_content_safety_controls",
    "google_ai_generated_content_safety",
}
POLICY_GATE_TARGETS = {
    "apple_review_access": ("apple_review_gates", "demo_account_or_demo_mode"),
    "apple_live_backend": ("apple_review_gates", "backend_live_during_review"),
    "apple_privacy_policy_and_retention": ("apple_review_gates", "privacy_details_match_runtime"),
    "apple_in_app_account_deletion": ("apple_review_gates", "in_app_account_deletion"),
    "apple_sign_in_with_apple_parity": ("apple_review_gates", "sign_in_with_apple_parity"),
    "google_privacy_policy": ("google_play_gates", "privacy_policy_public_url"),
    "google_data_safety": ("google_play_gates", "data_safety_form"),
    "google_in_app_account_deletion": ("google_play_gates", "in_app_account_deletion"),
    "google_web_account_deletion": ("google_play_gates", "web_account_deletion_resource"),
    "google_secure_handling_and_no_sale": ("google_play_gates", "secure_handling_and_no_sale"),
    "public_build_no_founder_leakage": ("apple_review_gates", "no_hidden_founder_features"),
    "apple_ai_disclosure_and_safety_reporting": ("apple_review_gates", "ai_disclosure_and_safety_reporting"),
    "apple_user_generated_content_safety_controls": ("apple_review_gates", "user_generated_content_safety_controls"),
    "google_ai_generated_content_safety": ("google_play_gates", "ai_generated_content_safety"),
}
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
]


def main() -> int:
    failures: list[str] = []
    packet = _load_json(PACKET, failures)
    inventory = _load_json(INVENTORY, failures)
    policy = _load_json(POLICY_REQUIREMENTS, failures)
    if not packet or not inventory or not policy:
        return _finish(failures)

    _check_basic_packet(packet, failures)
    _check_policy_source_freshness(packet, policy, inventory, failures)
    _check_public_urls(packet, failures)
    _check_env_consistency(packet, failures)
    _check_site_pages(failures)
    _check_review_access(packet, failures)
    _check_auth_and_account(packet, failures)
    _check_data_and_ai(packet, inventory, failures)
    _check_private_adapters(packet, failures)
    _check_policy_requirements(packet, policy, failures)
    _check_permissions(packet, failures)
    _check_platform_gates(packet, failures)
    _check_evidence_commands(packet, failures)
    _check_no_secrets(PACKET, failures)
    _check_no_secrets(DEPLOYMENT_PACKET, failures)
    _check_code_evidence(failures)
    return _finish(failures)


def _load_json(path: Path, failures: list[str]) -> dict:
    if not path.is_file():
        failures.append(f"Missing JSON file: {path.relative_to(ROOT)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}


def _check_basic_packet(packet: dict, failures: list[str]) -> None:
    if packet.get("app_name") != "Thought Pins":
        failures.append("submission packet app_name must be Thought Pins")
    if packet.get("review_notes_template") != "deploy/store/review-notes-template.md":
        failures.append("submission packet must reference deploy/store/review-notes-template.md")
    if packet.get("deployment_packet") != "deploy/closed-beta-deployment-packet.json":
        failures.append("submission packet must reference deploy/closed-beta-deployment-packet.json")
    handles = packet.get("brand_handles") or {}
    if handles.get("code_package") != "thoughtpins" or handles.get("display_name") != "Thought Pins":
        failures.append(
            "submission packet brand handles must distinguish thoughtpins code package from Thought Pins display name"
        )
    refs = packet.get("official_references") or {}
    missing = REQUIRED_OFFICIAL_REFERENCES - refs.keys()
    if missing:
        failures.append(f"submission packet missing official references: {sorted(missing)}")
    for key in REQUIRED_OFFICIAL_REFERENCES & refs.keys():
        if not _public_https(str(refs[key])):
            failures.append(f"official reference {key} must be a public HTTPS URL")


def _check_policy_source_freshness(
    packet: dict,
    policy: dict,
    inventory: dict,
    failures: list[str],
    *,
    today: date | None = None,
) -> None:
    today = today or date.today()
    packet_reviewed = packet.get("last_reviewed")
    policy_reviewed = policy.get("sources_checked_on")
    inventory_reviewed = inventory.get("last_reviewed")

    _check_policy_date("submission packet last_reviewed", packet_reviewed, today, failures)
    _check_policy_date("store-policy sources_checked_on", policy_reviewed, today, failures)
    _check_policy_date("data-safety inventory last_reviewed", inventory_reviewed, today, failures)

    if packet_reviewed and policy_reviewed and packet_reviewed != policy_reviewed:
        failures.append("store-policy requirements sources_checked_on must match submission packet last_reviewed")
    if packet_reviewed and inventory_reviewed and packet_reviewed != inventory_reviewed:
        failures.append("data-safety inventory last_reviewed must match submission packet last_reviewed")

    packet_refs = packet.get("official_references") or {}
    policy_refs = policy.get("official_references") or {}
    inventory_refs = inventory.get("official_references") or {}
    for key in REQUIRED_OFFICIAL_REFERENCES:
        expected = packet_refs.get(key)
        if not expected:
            continue
        if policy_refs.get(key) != expected:
            failures.append(f"store-policy official reference {key} must match submission packet")
        if inventory_refs.get(key) != expected:
            failures.append(f"data-safety inventory official reference {key} must match submission packet")


def _check_policy_date(label: str, value: object, today: date, failures: list[str]) -> None:
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


def _check_public_urls(packet: dict, failures: list[str]) -> None:
    urls = packet.get("public_urls") or {}
    for key, expected in REQUIRED_PUBLIC_URLS.items():
        actual = urls.get(key)
        if actual != expected:
            failures.append(f"public_urls.{key} must be {expected!r}, got {actual!r}")
        if actual and not _public_https(actual):
            failures.append(f"public_urls.{key} must be public HTTPS")


def _check_env_consistency(packet: dict, failures: list[str]) -> None:
    env = _parse_env(ROOT / ".env.production.example")
    urls = packet.get("public_urls") or {}
    expected = {
        "PRIVACY_POLICY_URL": urls.get("privacy_policy"),
        "TERMS_URL": urls.get("terms"),
        "SUPPORT_URL": urls.get("support"),
        "ACCOUNT_DELETION_URL": urls.get("account_deletion"),
        "AI_DISCLOSURE_URL": urls.get("ai_disclosure"),
        "WEB_APP_URL": urls.get("web_app"),
    }
    for key, value in expected.items():
        if env.get(key) != value:
            failures.append(f".env.production.example {key} must match submission packet: {value!r}")
    ios = (packet.get("store_targets") or {}).get("ios") or {}
    android = (packet.get("store_targets") or {}).get("android") or {}
    if env.get("IOS_STORE_URL") != ios.get("store_url"):
        failures.append("IOS_STORE_URL must match submission packet store target")
    if env.get("ANDROID_STORE_URL") != android.get("store_url"):
        failures.append("ANDROID_STORE_URL must match submission packet store target")


def _check_site_pages(failures: list[str]) -> None:
    for relative, markers in REQUIRED_SITE_MARKERS.items():
        text = _read(relative, failures)
        if not text:
            continue
        lowered = text.lower()
        if "placeholder" in lowered:
            failures.append(f"{relative} must not contain visible placeholder language")
        for marker in markers:
            if marker not in text:
                failures.append(f"{relative} missing store marker: {marker}")


def _check_review_access(packet: dict, failures: list[str]) -> None:
    review = packet.get("review_access") or {}
    if review.get("demo_account_required") is not True:
        failures.append("review_access.demo_account_required must be true")
    if review.get("password_stored_in_repo") is not False:
        failures.append("review_access.password_stored_in_repo must be false")
    if review.get("password_env_var") != "THOUGHTPINS_REVIEW_PASSWORD":
        failures.append("review access must use THOUGHTPINS_REVIEW_PASSWORD")
    if review.get("email_env_var") != "THOUGHTPINS_REVIEW_EMAIL":
        failures.append("review access must use THOUGHTPINS_REVIEW_EMAIL")
    if review.get("seed_command") != "python scripts/seed_review_account.py --export-vault --zip-vault":
        failures.append("review access seed_command must include vault export and zip")
    _require_file("src/thoughtpins/review_seed.py", failures)
    _require_file("scripts/seed_review_account.py", failures)
    _require_file("scripts/check_review_account_packet.py", failures)


def _check_auth_and_account(packet: dict, failures: list[str]) -> None:
    auth = packet.get("auth_and_account") or {}
    for key in [
        "email_login",
        "phone_login",
        "password_auth",
        "google_oauth_supported_when_configured",
        "apple_oauth_supported_when_configured",
        "apple_parity_required_if_google_offered_on_ios",
    ]:
        if auth.get(key) is not True:
            failures.append(f"auth_and_account.{key} must be true")
    if auth.get("in_app_account_deletion_endpoint") != "DELETE /v1/me":
        failures.append("auth_and_account must map in-app account deletion to DELETE /v1/me")
    if auth.get("account_export_endpoint") != "GET /v1/export":
        failures.append("auth_and_account must map export to GET /v1/export")
    oauth = _read("src/thoughtpins/oauth.py", failures)
    account_view = _read("frontend/src/features/account/AccountView.tsx", failures)
    auth_screen = _read("frontend/src/app/AuthScreen.tsx", failures)
    try:
        routes = discover_api_routes(ROOT)
    except RouteDiscoveryError as exc:
        failures.append(str(exc))
        routes = set()
    if ("DELETE", "/v1/me") not in routes:
        failures.append("API is missing DELETE /v1/me")
    if ("GET", "/v1/export") not in routes:
        failures.append("API is missing GET /v1/export")
    if "google" not in oauth.lower() or "appleid.apple.com" not in oauth:
        failures.append("OAuth verifier must include Google and Apple verifier paths")
    for marker in ["Email or phone", 'type="email"', 'type="tel"']:
        if marker not in auth_screen:
            failures.append(f"Auth screen missing {marker}")
    for marker in ["api.exportAccount", "api.deleteAccount", "api.acceptLegalDocument", "localMode || confirm"]:
        if marker not in account_view:
            failures.append(f"Account view missing {marker}")


def _check_data_and_ai(packet: dict, inventory: dict, failures: list[str]) -> None:
    data = packet.get("data_and_ai") or {}
    if data.get("data_safety_inventory") != "deploy/store/data-safety-inventory.json":
        failures.append("data_and_ai must reference deploy/store/data-safety-inventory.json")
    if data.get("store_policy_requirements") != "deploy/store/store-policy-requirements.json":
        failures.append("data_and_ai must reference deploy/store/store-policy-requirements.json")
    if data.get("native_review_handoff") != "deploy/store/native-review-handoff.json":
        failures.append("data_and_ai must reference deploy/store/native-review-handoff.json")
    if data.get("tracking_used_for_v1") is not False:
        failures.append("tracking_used_for_v1 must be false")
    if data.get("advertising_sdks_used_for_v1") is not False:
        failures.append("advertising_sdks_used_for_v1 must be false")
    if data.get("journal_content_sold") is not False:
        failures.append("journal_content_sold must be false")
    if data.get("user_content_sent_to_model_provider") is not True:
        failures.append("user_content_sent_to_model_provider must be true")
    if data.get("safety_report_endpoint") != "POST /v1/safety/reports":
        failures.append("data_and_ai must map safety reporting to POST /v1/safety/reports")
    if inventory.get("tracking", {}).get("used_for_tracking") is not False:
        failures.append("data-safety inventory must agree that tracking is false")
    if inventory.get("ai_processing", {}).get("user_content_sent_to_model_provider") is not True:
        failures.append("data-safety inventory must agree that model-provider processing is true")
    if inventory.get("account_deletion", {}).get("api_endpoint") != "DELETE /v1/me":
        failures.append("data-safety inventory account deletion endpoint mismatch")
    ai_safety = inventory.get("ai_safety", {})
    if ai_safety.get("unsafe_output_reporting") is not True:
        failures.append("data-safety inventory must document unsafe AI output reporting")
    if ai_safety.get("reporting_channel") != "support@thoughtpins.com":
        failures.append("data-safety inventory must map AI safety reports to support@thoughtpins.com")
    if ai_safety.get("in_app_reporting") is not True:
        failures.append("data-safety inventory must document in-app safety reporting")
    if ai_safety.get("report_endpoint") != "POST /v1/safety/reports":
        failures.append("data-safety inventory safety report endpoint mismatch")
    ugc = inventory.get("user_generated_content", {})
    if ugc.get("private_by_default") is not True or ugc.get("public_posting") is not False:
        failures.append("data-safety inventory must document private-by-default user content")
    if ugc.get("report_endpoint") != "POST /v1/safety/reports":
        failures.append("data-safety inventory user-content report endpoint mismatch")
    source_policy = inventory.get("copyright_and_sources", {})
    if source_policy.get("access_control_circumvention") is not False:
        failures.append("data-safety inventory must prohibit access-control circumvention")
    if source_policy.get("user_submitted_sources_only") is not True:
        failures.append("data-safety inventory must limit imports to user-submitted sources")
    if not data.get("ai_safety_policy"):
        failures.append("data_and_ai must describe AI safety and reporting policy")
    article_policy = str(data.get("article_source_policy", "")).lower()
    if "publisher access controls are respected" not in article_policy:
        failures.append("data_and_ai.article_source_policy must require publisher access controls")


def _check_private_adapters(packet: dict, failures: list[str]) -> None:
    adapters = packet.get("private_adapters") or {}
    adapter = adapters.get("personal_chat_adapter") or {}
    if not adapter:
        failures.append("submission packet must document the private personal_chat_adapter boundary")
        return
    if adapter.get("included_in_store_builds") is not False:
        failures.append("private personal_chat_adapter must not be included in store builds")
    if adapter.get("included_in_public_github_export") is not False:
        failures.append("private personal_chat_adapter must not be included in public GitHub export")
    if adapter.get("uses_public_api_only") is not True:
        failures.append("private personal_chat_adapter must use public API only")
    required_paths = {"/v1/chat", "/v1/client-config", "/v1/health/deep", "/v1/export"}
    actual_paths = set(str(item) for item in adapter.get("required_public_api_paths") or [])
    missing = required_paths - actual_paths
    if missing:
        failures.append(f"private personal_chat_adapter missing public API paths: {sorted(missing)}")
    exclusions = packet.get("public_build_exclusions") or {}
    if exclusions.get("private_local_adapter_visible") is not False:
        failures.append("public build exclusions must hide private local adapters")
    if exclusions.get("client_config_exposes_private_adapter_flags") is not False:
        failures.append("public client config must not expose private adapter flags")
    data = packet.get("data_and_ai") or {}
    if data.get("local_device_storage_plan") != "docs/architecture/LOCAL_DEVICE_STORAGE.md":
        failures.append("data_and_ai must reference docs/architecture/LOCAL_DEVICE_STORAGE.md")
    if data.get("apple_review_answers") != "docs/release/APPLE_REVIEW_ANSWERS.md":
        failures.append("data_and_ai must reference docs/release/APPLE_REVIEW_ANSWERS.md")


def _check_policy_requirements(packet: dict, policy: dict, failures: list[str]) -> None:
    _check_policy_header(packet, policy, failures)
    requirements = policy.get("requirements") or []
    if not isinstance(requirements, list) or not requirements:
        failures.append("store-policy requirements must be a non-empty list")
        return

    by_id = {item.get("id"): item for item in requirements if isinstance(item, dict)}
    missing = REQUIRED_POLICY_IDS - by_id.keys()
    if missing:
        failures.append(f"store-policy requirements missing ids: {sorted(missing)}")
    gate_sets = _policy_gate_sets(packet)
    for req_id, requirement in by_id.items():
        _check_one_policy_requirement(req_id, requirement, gate_sets, failures)


def _check_policy_header(packet: dict, policy: dict, failures: list[str]) -> None:
    if policy.get("app_name") != "Thought Pins":
        failures.append("store-policy requirements must identify Thought Pins")
    if policy.get("sources_checked_on") != packet.get("last_reviewed"):
        failures.append("store-policy requirements sources_checked_on must match submission packet last_reviewed")

    packet_refs = packet.get("official_references") or {}
    policy_refs = policy.get("official_references") or {}
    for key in REQUIRED_OFFICIAL_REFERENCES:
        if policy_refs.get(key) != packet_refs.get(key):
            failures.append(f"store-policy official reference {key} must match submission packet")


def _policy_gate_sets(packet: dict) -> dict[str, dict]:
    apple_gates = {item.get("name"): item for item in packet.get("apple_review_gates", [])}
    google_gates = {item.get("name"): item for item in packet.get("google_play_gates", [])}
    return {"apple_review_gates": apple_gates, "google_play_gates": google_gates}


def _check_one_policy_requirement(
    req_id: object,
    requirement: dict,
    gate_sets: dict[str, dict],
    failures: list[str],
) -> None:
    if req_id not in REQUIRED_POLICY_IDS:
        failures.append(f"store-policy requirement has unexpected id: {req_id}")
        return
    req_id_text = str(req_id)
    _check_policy_requirement_shape(req_id_text, requirement, failures)
    expected = POLICY_GATE_TARGETS.get(req_id_text)
    if expected:
        _check_policy_gate_link(req_id_text, requirement, expected, gate_sets, failures)


def _check_policy_requirement_shape(req_id: str, requirement: dict, failures: list[str]) -> None:
    if requirement.get("required") is not True:
        failures.append(f"store-policy requirement {req_id} must be required=true")
    if requirement.get("platform") not in {"apple", "google", "apple_google"}:
        failures.append(f"store-policy requirement {req_id} has invalid platform")
    if requirement.get("official_reference") not in REQUIRED_OFFICIAL_REFERENCES:
        failures.append(f"store-policy requirement {req_id} uses unknown official_reference")
    for field in ("policy_summary", "implementation_status"):
        if not str(requirement.get(field) or "").strip():
            failures.append(f"store-policy requirement {req_id} must include {field}")
    evidence = requirement.get("evidence") or []
    if not isinstance(evidence, list) or not evidence:
        failures.append(f"store-policy requirement {req_id} must include evidence")


def _check_policy_gate_link(
    req_id: str,
    requirement: dict,
    expected: tuple[str, str],
    gate_sets: dict[str, dict],
    failures: list[str],
) -> None:
    gate_group, gate_name = expected
    if requirement.get("local_gate") != gate_name:
        failures.append(f"store-policy requirement {req_id} local_gate must be {gate_name}")
    gate = gate_sets[gate_group].get(gate_name)
    if not gate:
        failures.append(f"store-policy requirement {req_id} points at missing packet gate {gate_group}.{gate_name}")
        return
    platform = requirement.get("platform")
    if (gate_group == "apple_review_gates" and platform == "google") or (
        gate_group == "google_play_gates" and platform == "apple"
    ):
        failures.append(f"store-policy requirement {req_id} platform/gate mismatch")
    gate_evidence = {str(item) for item in gate.get("evidence") or []}
    requirement_evidence = {str(item) for item in requirement.get("evidence") or []}
    if gate_evidence and not gate_evidence.intersection(requirement_evidence):
        failures.append(f"store-policy requirement {req_id} evidence should overlap packet gate {gate_name}")


def _check_permissions(packet: dict, failures: list[str]) -> None:
    permissions = packet.get("permissions_rationale") or {}
    web = permissions.get("web_closed_beta") or {}
    future = permissions.get("native_apps") or permissions.get("future_native") or {}
    if "user-initiated" not in str(web.get("microphone", "")).lower():
        failures.append("web_closed_beta.microphone must disclose user-initiated recording")
    for key in ["camera", "location", "contacts"]:
        if web.get(key) != "not requested":
            failures.append(f"web_closed_beta.{key} should be 'not requested'")
    if "user-selected" not in str(web.get("photos", "")):
        failures.append("web_closed_beta.photos must be limited to user-selected upload")
    for key in ["microphone", "photos_or_files", "notifications", "location", "contacts"]:
        if key not in future:
            failures.append(f"native_apps missing permission rationale: {key}")


def _check_platform_gates(packet: dict, failures: list[str]) -> None:
    apple = {item.get("name"): item for item in packet.get("apple_review_gates", [])}
    google = {item.get("name"): item for item in packet.get("google_play_gates", [])}
    missing_apple = REQUIRED_APPLE_GATES - apple.keys()
    missing_google = REQUIRED_GOOGLE_GATES - google.keys()
    if missing_apple:
        failures.append(f"missing Apple review gates: {sorted(missing_apple)}")
    if missing_google:
        failures.append(f"missing Google Play gates: {sorted(missing_google)}")
    bad_statuses = {"missing", "unknown", "todo", "placeholder"}
    for platform, gates in (("apple", apple), ("google", google)):
        for name, gate in gates.items():
            status = str(gate.get("status", "")).lower()
            if not status or status in bad_statuses:
                failures.append(f"{platform} gate {name} has invalid status {status!r}")
            if not gate.get("evidence"):
                failures.append(f"{platform} gate {name} must include evidence")


def _check_evidence_commands(packet: dict, failures: list[str]) -> None:
    commands = set(packet.get("evidence_commands") or [])
    missing = REQUIRED_COMMANDS - commands
    if missing:
        failures.append(f"submission packet missing evidence commands: {sorted(missing)}")
    for command in commands:
        parts = command.split()
        if len(parts) >= 2 and parts[0] == "python":
            script = ROOT / parts[1]
            if parts[1].startswith("scripts/") and not script.is_file():
                failures.append(f"evidence command references missing script: {parts[1]}")


def _check_no_secrets(path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append(f"{path.relative_to(ROOT)} appears to contain a secret-like token")
    if "review-password" in text.lower() or "actual password" in text.lower():
        failures.append("submission packet must not include review account password material")


def _check_code_evidence(failures: list[str]) -> None:
    for relative in [
        "scripts/release_check.py",
        "scripts/check_review_account_packet.py",
        "scripts/check_review_notes_packet.py",
        "scripts/check_deployment_packet.py",
        "scripts/check_launch_packet.py",
        "scripts/check_host_capabilities.py",
        "scripts/generate_launch_packet.py",
        "scripts/app_store_compliance_check.py",
        "scripts/check_domain_readiness.py",
        "scripts/check_public_export.py",
        "scripts/collect_closed_beta_evidence.py",
        "scripts/collect_local_closed_beta_evidence.py",
        "deploy/store/data-safety-inventory.json",
        "deploy/store/store-policy-requirements.json",
        "deploy/store/native-review-handoff.json",
        "deploy/store/review-notes-template.md",
        "deploy/closed-beta-deployment-packet.json",
        "docs/release/APPLE_REVIEW_ANSWERS.md",
        "docs/architecture/LOCAL_DEVICE_STORAGE.md",
    ]:
        _require_file(relative, failures)


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _read(relative: str, failures: list[str]) -> str:
    path = ROOT / relative
    if not path.is_file():
        failures.append(f"Missing file: {relative}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _require_file(relative: str, failures: list[str]) -> None:
    if not (ROOT / relative).is_file():
        failures.append(f"Missing file: {relative}")


def _public_https(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.hostname not in {"localhost", "127.0.0.1"}


def _finish(failures: list[str]) -> int:
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Store submission packet check failed: {len(failures)} failure(s).")
        return 1
    print("Store submission packet check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
