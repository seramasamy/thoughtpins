"""Static product-contract checks for the Thought Pins web app.

Playwright remains the real browser proof, but local Windows shells can block
browser/process spawning. This gate verifies that the maintained React app and
static fallback still expose the closed-beta product surfaces needed for web,
mobile-web, and store-review rehearsal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from web_assets import StylesheetBundleError, read_stylesheet_bundle

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


@dataclass(frozen=True)
class Requirement:
    label: str
    markers: tuple[str, ...]
    all_required: bool = False


def main() -> int:
    failures: list[str] = []
    cache: dict[Path, str] = {}

    _check_file_markers(
        FRONTEND / "src" / "app" / "types.ts",
        failures,
        cache,
        [
            _req(
                "five primary release views typed",
                '"recap"',
                '"people"',
                '"chat"',
                '"places"',
                '"pins"',
                all_required=True,
            ),
            _req(
                "utility views typed",
                '"memory"',
                '"capture"',
                '"library"',
                '"entries"',
                '"jobs"',
                '"account"',
                '"legal"',
                '"status"',
                all_required=True,
            ),
            _req("API errors become notices", "messageFromError"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "app" / "navigation.tsx",
        failures,
        cache,
        [
            _req(
                "five primary nav destinations",
                'view: "recap"',
                'view: "people"',
                'view: "chat"',
                'view: "places"',
                'view: "pins"',
                all_required=True,
            ),
            _req("primary nav contract", "PRIMARY_NAV_ITEMS"),
            _req("utility nav contract", "UTILITY_NAV_ITEMS"),
            _req("memory nav", 'view: "memory"'),
            _req("capture nav", 'view: "capture"'),
            _req("library nav", 'view: "library"'),
            _req("entries nav", 'view: "entries"'),
            _req("jobs nav", 'view: "jobs"'),
            _req("status nav", 'view: "status"'),
            _req("account nav", 'view: "account"'),
            _req("legal nav", 'view: "legal"'),
            _req("chat-first subtitle", "Talk naturally with the memory that grows with you"),
            _req("recap subtitle", "Daily, weekly, and monthly patterns"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "App.tsx",
        failures,
        cache,
        [
            _req("session persistence", "thoughtpins.session.v1"),
            _req("client config bootstrap", "api.clientConfig"),
            _req("maintenance message plumbed", "maintenanceMessage"),
            _req("local founder/no-auth mode", "localMode"),
            _req("chat view mounted", "<ChatView"),
            _req("recap view mounted", "<RecapView"),
            _req("people view mounted", 'initialSection="people"'),
            _req("places view mounted", 'initialSection="places"'),
            _req("pins view mounted", "<PinsView"),
            _req("memory view mounted", "<MemoryView"),
            _req("capture view mounted", "<CaptureView"),
            _req("library view mounted", "<LibraryView"),
            _req("entries view mounted", "<EntriesView"),
            _req("jobs view mounted", "<JobsView"),
            _req("status view mounted", "<DashboardView"),
            _req("account view mounted", "<AccountView"),
            _req("legal view mounted", "<LegalView"),
            _req("global compose handler", "handleGlobalCompose", "GlobalComposeMode", all_required=True),
            _req("global chat API wiring", "api.chat(token", 'conversation_id: "main"', all_required=True),
            _req("global journal API wiring", "api.ingest(token, body)", "Entry saved", all_required=True),
            _req("global maintenance pause", "maintenanceMessage", 'setNotice({ tone: "warn"', all_required=True),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "app" / "AppShell.tsx",
        failures,
        cache,
        [
            _req("desktop workspace navigation", 'aria-label="Workspace navigation"'),
            _req("primary navigation", 'aria-label="Primary"'),
            _req("mobile primary navigation", 'aria-label="Mobile primary navigation"'),
            _req("global composer shell", "global-composer", "Quick chat or journal composer", all_required=True),
            _req(
                "global composer modes",
                "composer-mode-button",
                'current === "chat" ? "journal" : "chat"',
                all_required=True,
            ),
            _req("global composer Enter submit", "submitFormOnEnter", 'enterKeyHint="send"', all_required=True),
            _req("global composer pending state", "composePending", "Thinking with your memory", all_required=True),
            _req("global composer hidden on chat", 'showGlobalComposer = view !== "chat"'),
            _req(
                "matching desktop and mobile primary nav",
                "PRIMARY_NAV_ITEMS.map",
                'aria-label="Mobile primary navigation"',
                all_required=True,
            ),
            _req(
                "center featured chat action",
                'item.view === "chat"',
                'featured={item.view === "chat"}',
                all_required=True,
            ),
            _req("utility popover", "UTILITY_NAV_ITEMS.map", "utility-popover", all_required=True),
            _req("sidebar side preference", "thoughtpins.sidebar.side", "toggleSidebar", all_required=True),
            _req("maintenance banner", "maintenance-banner"),
            _req("refresh action", "refreshMe"),
            _req("logout action", "Sign out"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "app" / "AuthScreen.tsx",
        failures,
        cache,
        [
            _req("login/register modes", '"login" | "register"'),
            _req("email or phone login", "Email or phone"),
            _req("email registration", 'type="email"'),
            _req("phone registration", 'type="tel"'),
            _req("registration lock", "registrationLocked"),
            _req("strong password minimum", "minLength={12}"),
            _req("maintenance visible before auth", "maintenance-banner"),
            _req("register API", "api.register"),
            _req("login API", "api.login"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "api-transport.ts",
        failures,
        cache,
        [
            _req("request ID propagation", "X-Request-ID"),
            _req("network maintenance/offline envelope", "network_unavailable"),
            _req("idempotency keys", "Idempotency-Key"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "api.ts",
        failures,
        cache,
        [
            _req("session refresh", "/v1/auth/refresh"),
            _req("client config", "/v1/client-config"),
            _req("email/phone register", "/v1/auth/register"),
            _req("login", "/v1/auth/login"),
            _req("oauth token exchange", "/v1/auth/oauth"),
            _req("chat endpoint", "/v1/chat"),
            _req("chat history", "/v1/chat/conversations"),
            _req("journal entries", "/v1/entries"),
            _req("library endpoint", "/v1/library"),
            _req("file uploads", "/v1/uploads"),
            _req("memory cards", "/v1/memory/cards"),
            _req("deep health", "/v1/health/deep"),
            _req("status", "/v1/status"),
            _req("jobs", "/v1/jobs"),
            _req("preferences", "/v1/preferences"),
            _req("legal acceptances", "/v1/legal/acceptances"),
            _req("devices", "/v1/devices"),
            _req("vault/account export", "/v1/export"),
            _req("account delete", "/v1/me"),
            _req("upload destinations", 'destination: options.destination || "auto"'),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "chat" / "ChatView.tsx",
        failures,
        cache,
        [
            _req("chat history restore", "api.chatConversations", "api.chatMessages", all_required=True),
            _req(
                "private recall toggle",
                "include_private",
                "Use private memories",
                "Private memories stay out of replies",
                all_required=True,
            ),
            _req("pending confirmation", "pending_action_id"),
            _req(
                "pending confirm/cancel buttons",
                "forceConfirm",
                "needs your confirmation",
                "Cancel",
                "Confirm",
                all_required=True,
            ),
            _req("confirmation prompt", "requires_confirmation"),
            _req("maintenance local response", 'routeType: "maintenance"'),
            _req("familiar chat placeholder", "Message Thought Pins..."),
            _req("chat Enter submit", "submitFormOnEnter", 'aria-label="Message Thought Pins"', all_required=True),
            _req("thinking state", "Thinking with your memory"),
            _req("classification transparency", "classification-label", "friendlyRoute", all_required=True),
            _req("file attachment", "api.uploadFile", "Attach a file", all_required=True),
            _req("voice note capture", "MediaRecorder", "Record a voice note", all_required=True),
            _req("50k chat max", "maxLength={50000}"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "account" / "AccountView.tsx",
        failures,
        cache,
        [
            _req("response voice preference", "Response voice", "response_style", all_required=True),
            _req("explicit style matching", "Match my style", "explicit choice", all_required=True),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "recap" / "RecapView.tsx",
        failures,
        cache,
        [
            _req("daily weekly monthly recap", '"daily"', '"weekly"', '"monthly"', all_required=True),
            _req("report synthesis API", "api.report"),
            _req("journal timeline API", "api.entries"),
            _req("period filtering", "isInsidePeriod"),
            _req("synthesized sections", "parseReport"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "pins" / "PinsView.tsx",
        failures,
        cache,
        [
            _req("quick link or note pinning", "api.createLibrarySource"),
            _req("document pinning", "api.uploadFile"),
            _req("pin search", "filtered"),
            _req("source details", "api.librarySource"),
            _req(
                "reader-facing source details",
                "publisher",
                "topics",
                "key_concepts",
                "canonical_url",
                all_required=True,
            ),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "chat" / "confirmation.ts",
        failures,
        cache,
        [
            _req(
                "exact general confirmation phrases",
                "GENERAL_CONFIRMATION_PHRASES",
                "yes please",
                "do it",
                all_required=True,
            ),
            _req(
                "explicit cancellation phrases", "CANCEL_CONFIRMATION_PHRASES", "never mind", "nope", all_required=True
            ),
            _req("neutral confirmation fallback", "return null"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "capture" / "CaptureView.tsx",
        failures,
        cache,
        [
            _req("explicit journal flow", "Explicit Journal Save"),
            _req("journal ingest", "api.ingest"),
            _req("50k journal max", "maxLength={50000}"),
            _req("queued job visibility", "job_id"),
            _req("browser local draft queue", "DraftQueue", "browserStorage", all_required=True),
            _req("offline queued draft fallback", 'queue.create(body, "queued")'),
            _req("local draft sync", "syncDraftQueue", "Sync queued", all_required=True),
            _req("local draft removal", "queue?.remove", "Remove local draft", all_required=True),
            _req("local draft status visibility", "Local Draft Queue", "attemptCount", "lastError", all_required=True),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "library" / "LibraryView.tsx",
        failures,
        cache,
        [
            _req(
                "article/book/paper source types",
                '<option value="article">Article</option>',
                '<option value="book">Book</option>',
                '<option value="paper">Paper</option>',
                all_required=True,
            ),
            _req("URL ingestion", 'type="url"'),
            _req("pasted text ingestion", "maxLength={200000}"),
            _req("file upload", 'type="file"'),
            _req(
                "upload destinations",
                '<option value="auto">',
                '<option value="library">',
                '<option value="journal">',
                all_required=True,
            ),
            _req("library API", "api.createLibrarySource"),
            _req("file API", "api.uploadFile"),
            _req("source list", "api.librarySources"),
            _req("source detail", "api.librarySource"),
            _req(
                "reader-facing source details",
                "publisher",
                "topics",
                "key_concepts",
                "canonical_url",
                all_required=True,
            ),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "memory" / "MemoryView.tsx",
        failures,
        cache,
        [
            _req(
                "all memory sections",
                '"people", "places", "projects", "organizations", "events", "things", "concepts", "all"',
            ),
            _req("memory card API", "api.memoryCards"),
            _req("memory detail API", "api.memoryCard"),
            _req("baseball statline", "statline"),
            _req("relationships", "relationships"),
            _req("timeline", "timeline"),
            _req("source documents", "source_documents"),
            _req("vault note path", "obsidian_path"),
            _req("human-readable archive reference", "displayReferenceTitle"),
            _req("provenance confidence", "provenance?.confidence"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "entries" / "EntriesView.tsx",
        failures,
        cache,
        [
            _req("paginated entries", "api.entries(token, page)"),
            _req("entry deletion", "api.deleteEntry"),
            _req("previous pager", "Previous"),
            _req("next pager", "Next"),
            _req("processed status", "processed_status"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "jobs" / "JobsView.tsx",
        failures,
        cache,
        [
            _req("job status filter", "JOB_STATUSES"),
            _req("dead-letter visible", "dead_letter"),
            _req("retry action", "api.retryJob"),
            _req("cancel action", "api.cancelJob"),
            _req("retryability guard", "isRetryable"),
            _req("cancelability guard", "isCancelable"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "dashboard" / "DashboardView.tsx",
        failures,
        cache,
        [
            _req("status API", "api.status"),
            _req("deep health API", "api.deepHealth"),
            _req("entries metric", 'Metric label="Entries"'),
            _req("memories metric", 'Metric label="Memories"'),
            _req("entities metric", 'Metric label="Entities"'),
            _req("sources metric", 'Metric label="Sources"'),
            _req("processing metric", 'Metric label="Processing"'),
            _req("runtime checks", "health?.checks"),
            _req("vault files", "vault_files"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "account" / "AccountView.tsx",
        failures,
        cache,
        [
            _req("preferences API", "api.preferences"),
            _req("preferences update", "api.updatePreferences"),
            _req("legal acceptances", "api.acceptLegalDocument"),
            _req("device registration", "api.registerDevice"),
            _req("device revoke", "api.revokeDevice"),
            _req("account export", "api.exportAccount"),
            _req("account delete", "api.deleteAccount"),
            _req("local founder delete guard", 'localMode || confirm !== "DELETE"'),
            _req("web installation id", "thoughtpins.web_installation.v1"),
            _req("private entries preference", "private_entries_in_ask"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "features" / "legal" / "LegalView.tsx",
        failures,
        cache,
        [
            _req("privacy URL", "privacy_policy_url"),
            _req("terms URL", "terms_url"),
            _req("support URL", "support_url"),
            _req("account deletion URL", "account_deletion_url"),
            _req("AI disclosure URL", "ai_disclosure_url"),
            _req("Apple OAuth readiness", "oauth_apple_enabled"),
            _req("Google OAuth readiness", "oauth_google_enabled"),
            _req("store target versions", "minimum_supported_clients"),
            _req("store URLs", "store_urls"),
            _req("store review gate", "STORE_GATES"),
            _req("inline legal summaries", "LEGAL_SUMMARIES", "Policy Summary", all_required=True),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "app" / "storeReadiness.ts",
        failures,
        cache,
        [
            _req("not thin wrapper gate", "Not a thin web wrapper"),
            _req("account deletion/export gate", "Account deletion and export"),
            _req("privacy/AI disclosure gate", "Privacy and AI disclosure"),
            _req("Apple parity gate", "Sign in with Apple parity"),
            _req("review account gate", "Review account and live backend"),
            _req("data safety gate", "Data safety inventory"),
            _req("native proof externalized", "signed native builds and device screenshots"),
            _req("packaged legal pages", "packaged and served by the app/API image"),
            _req("machine-readable data inventory", "A machine-readable inventory exists"),
            _req("Playwright tool", "Playwright"),
            _req("axe-core tool", "axe-core"),
            _req("fastlane tool", "fastlane"),
        ],
    )
    _check_file_markers(
        FRONTEND / "src" / "styles.css",
        failures,
        cache,
        [
            _req("minimum mobile width", "min-width: 320px"),
            _req("desktop shell grid", "grid-template-columns: 224px minmax(0, 1fr)"),
            _req("wide responsive breakpoint", "@media (max-width: 1180px)"),
            _req("mobile shell breakpoint", "@media (max-width: 860px)"),
            _req("phone breakpoint", "@media (max-width: 700px)"),
            _req("mobile tabbar", ".mobile-tabbar"),
            _req("featured center chat tab", ".mobile-tabbar button.featured", all_required=True),
            _req("orange design token", "--tp-orange: #e8612b"),
            _req(
                "global composer style", ".global-composer", ".app-shell.has-global-composer .main", all_required=True
            ),
            _req(
                "global composer mobile safe area",
                "bottom: calc(82px + env(safe-area-inset-bottom))",
                "padding-bottom: calc(170px + env(safe-area-inset-bottom))",
                all_required=True,
            ),
            _req("safe area support", "env(safe-area-inset-bottom)"),
            _req("touch target", "min-height: 48px"),
            _req("horizontal table overflow", "overflow-x: auto"),
            _req("long text wrapping", "overflow-wrap: anywhere"),
            _req("maintenance banner style", ".maintenance-banner"),
            _req(
                "local draft queue layout",
                ".draft-list",
                ".draft-item",
                ".draft-meta",
                ".draft-text",
                all_required=True,
            ),
        ],
    )
    _check_file_markers(
        FRONTEND / "static" / "app.js",
        failures,
        cache,
        [
            _req(
                "static view list",
                '["ask", "Chat"]',
                '["memory", "Memory"]',
                '["capture", "Capture"]',
                '["library", "Library"]',
                '["entries", "Entries"]',
                '["jobs", "Activity"]',
                '["dashboard", "Status"]',
                '["account", "Account"]',
                '["legal", "Legal"]',
                all_required=True,
            ),
            _req("static request IDs", "X-Request-ID"),
            _req("static session refresh", "/v1/auth/refresh"),
            _req("static client config", "/v1/client-config"),
            _req("static chat", "/v1/chat"),
            _req("static chat history", "/v1/chat/conversations"),
            _req("static journal entries", "/v1/entries"),
            _req("static library", "/v1/library"),
            _req("static uploads", "/v1/uploads"),
            _req("static memory cards", "/v1/memory/cards"),
            _req("static health", "/v1/health/deep"),
            _req("static account export", "/v1/export"),
            _req("static account delete", "/v1/me"),
            _req("static bottom composer", "renderBottomComposer"),
            _req(
                "static exact confirmation helper",
                "GENERAL_CONFIRMATION_PHRASES",
                "CANCEL_CONFIRMATION_PHRASES",
                "confirmationIntent",
                all_required=True,
            ),
            _req("static composer modes", "composerMode"),
            _req("static maintenance banner", "renderMaintenanceBanner"),
            _req("static maintenance chat pause", 'route_type: "maintenance"'),
            _req(
                "static reader-facing source details",
                "sourcePublisher",
                "sourceOriginalUrl",
                "key_concepts",
                all_required=True,
            ),
            _req("static source documents", "Source Documents"),
            _req("static archive reference", "Archive reference", "displayReferenceTitle", all_required=True),
            _req("static dead-letter jobs", "dead_letter"),
            _req(
                "static local draft queue",
                "CAPTURE_DRAFTS_KEY",
                "queueCaptureDraft",
                "syncCaptureDrafts",
                "renderCaptureDraft",
                all_required=True,
            ),
            _req("static local draft removal", "removeCaptureDraft", "remove-capture-draft", all_required=True),
            _req("static native proof externalized", "signed native builds and device screenshots"),
            _req("static packaged legal pages", "packaged and served by the app/API image"),
            _req("static data safety ready", '["Data safety inventory", "ready"'),
        ],
    )
    _check_occurrence(
        FRONTEND / "static" / "app.js",
        failures,
        cache,
        "maintenance banner rendered in fallback shell and auth",
        "renderMaintenanceBanner()",
        3,
    )
    _check_file_markers(
        FRONTEND / "static" / "styles.css",
        failures,
        cache,
        [
            _req("static minimum mobile width", "min-width: 320px"),
            _req("static responsive tablet", "@media (max-width: 900px)"),
            _req("static responsive phone", "@media (max-width: 560px)"),
            _req("static fixed bottom composer", ".bottom-composer"),
            _req("static maintenance banner style", ".maintenance-banner"),
            _req("static long text wrapping", "overflow-wrap: anywhere"),
            _req(
                "static local draft queue layout",
                ".draft-list",
                ".draft-item",
                ".draft-meta",
                ".draft-text",
                all_required=True,
            ),
        ],
    )

    _check_regex(
        FRONTEND / "src" / "styles.css",
        failures,
        cache,
        "no oversized card radius",
        r"border-radius:\s*(?:9|[1-9][0-9])px",
    )
    built_js = tuple(sorted((FRONTEND / "dist" / "assets").glob("*.js")))
    if not built_js and (FRONTEND / "dist" / "app.js").is_file():
        built_js = (FRONTEND / "dist" / "app.js",)

    for path in (
        FRONTEND / "src" / "features" / "chat" / "ChatView.tsx",
        FRONTEND / "static" / "app.js",
        *built_js,
    ):
        _check_absent(
            path,
            failures,
            cache,
            "no loose confirmation parser",
            (
                "^confirm|yes|do it$",
                'startsWith("confirm ")',
            ),
        )
    for path in (
        FRONTEND / "src" / "features" / "pins" / "PinsView.tsx",
        FRONTEND / "src" / "features" / "library" / "LibraryView.tsx",
        FRONTEND / "static" / "app.js",
        *built_js,
    ):
        _check_absent(
            path,
            failures,
            cache,
            "no internal source diagnostics in user UI",
            (
                "access_method",
                "rights_basis",
                "retrieval_quality_score",
                "paywall_detected",
            ),
        )
    for path in (
        FRONTEND / "src" / "app" / "storeReadiness.ts",
        FRONTEND / "static" / "app.js",
        *built_js,
    ):
        _check_absent(
            path,
            failures,
            cache,
            "no stale store readiness copy",
            (
                "public production legal copy still has to be final",
                "Generate a final data inventory from production config",
                "Apple review expects useful app functionality beyond a repackaged website",
            ),
        )

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Web app product contract check failed: {len(failures)} failure(s).")
        return 1
    print("Web app product contract check passed.")
    return 0


def _req(label: str, *markers: str, all_required: bool = False) -> Requirement:
    return Requirement(label=label, markers=tuple(markers), all_required=all_required)


def _read(path: Path, failures: list[str], cache: dict[Path, str]) -> str:
    if path in cache:
        return cache[path]
    if not path.is_file():
        failures.append(f"Missing file: {path.relative_to(ROOT)}")
        cache[path] = ""
        return ""
    try:
        text = (
            read_stylesheet_bundle(path)
            if path.suffix.lower() == ".css"
            else path.read_text(encoding="utf-8-sig", errors="ignore")
        )
    except (OSError, UnicodeError, StylesheetBundleError) as exc:
        failures.append(f"Could not resolve {path.relative_to(ROOT)}: {exc}")
        text = ""
    cache[path] = text
    return text


def _check_file_markers(
    path: Path, failures: list[str], cache: dict[Path, str], requirements: list[Requirement]
) -> None:
    text = _read(path, failures, cache)
    if not text:
        return
    relative = path.relative_to(ROOT)
    for requirement in requirements:
        if requirement.all_required:
            missing = [marker for marker in requirement.markers if marker not in text]
            if missing:
                failures.append(f"{relative} missing {requirement.label}: {', '.join(missing)}")
        elif not any(marker in text for marker in requirement.markers):
            failures.append(f"{relative} missing {requirement.label}: one of {requirement.markers}")


def _check_occurrence(
    path: Path, failures: list[str], cache: dict[Path, str], label: str, marker: str, minimum: int
) -> None:
    text = _read(path, failures, cache)
    count = text.count(marker)
    if count < minimum:
        failures.append(
            f"{path.relative_to(ROOT)} missing {label}: found {count}, expected at least {minimum} occurrences of {marker!r}"
        )


def _check_absent(
    path: Path, failures: list[str], cache: dict[Path, str], label: str, markers: tuple[str, ...]
) -> None:
    text = _read(path, failures, cache)
    for marker in markers:
        if marker in text:
            failures.append(f"{path.relative_to(ROOT)} violates {label}: unexpected {marker!r}")


def _check_regex(path: Path, failures: list[str], cache: dict[Path, str], label: str, pattern: str) -> None:
    text = _read(path, failures, cache)
    if re.search(pattern, text):
        failures.append(f"{path.relative_to(ROOT)} violates {label}: pattern {pattern!r}")


if __name__ == "__main__":
    raise SystemExit(main())
