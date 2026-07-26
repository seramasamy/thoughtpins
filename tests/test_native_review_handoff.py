from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_review_handoff_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_native_review_handoff.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Native review handoff check passed." in result.stdout


def test_native_review_handoff_tracks_source_shells_without_claiming_submission_ready() -> None:
    handoff = json.loads((ROOT / "deploy/store/native-review-handoff.json").read_text(encoding="utf-8-sig"))
    assert handoff["status"]["native_ui_shells_ready"] is True
    assert handoff["status"]["native_store_submission_ready"] is False

    shells = handoff["native_app_shell_modules"]
    assert (ROOT / shells["ios"] / "Sources/ThoughtPinsApp/ThoughtPinsReviewShell.swift").is_file()
    assert (ROOT / shells["android"] / "src/main/kotlin/com/thoughtpins/app/ui/ThoughtPinsAppShell.kt").is_file()

    ios_source_root = ROOT / shells["ios"] / "Sources/ThoughtPinsApp"
    ios_shell = "\n".join(path.read_text(encoding="utf-8-sig") for path in sorted(ios_source_root.glob("*.swift")))
    android_source_root = ROOT / shells["android"] / "src/main/kotlin/com/thoughtpins/app/ui"
    android_shell = "\n".join(path.read_text(encoding="utf-8-sig") for path in sorted(android_source_root.glob("*.kt")))
    assert "ThoughtPinsOAuthProvider" in ios_shell
    assert "ThoughtPinsOAuthTokenProvider" in ios_shell
    assert "oauthLogin(provider:" in ios_shell
    assert "ThoughtPinsUploadProvider" in ios_shell
    assert "ThoughtPinsUploadDestination" in ios_shell
    assert "ThoughtPinsDocumentPickerUploadProvider" in ios_shell
    assert "UniformTypeIdentifiers" in ios_shell
    assert "fileImporter(" in ios_shell
    assert "Data(contentsOf:" in ios_shell
    assert "base64EncodedString()" in ios_shell
    assert "startAccessingSecurityScopedResource" in ios_shell
    assert "uploadSelectedFile(destination:" in ios_shell
    assert "uploadFile(" in ios_shell
    assert "ThoughtPinsNotificationPermissionProvider" not in ios_shell
    assert "registerDeviceForReview" not in ios_shell
    assert "enableNotifications" not in ios_shell
    assert "Legal and support" in ios_shell
    assert "Privacy Policy" in ios_shell
    assert "Account Deletion" in ios_shell
    assert "AI Disclosure" in ios_shell
    assert "legalURL(configured:" in ios_shell
    assert "acceptLegal(document:" in ios_shell
    assert 'Link("Privacy Policy"' in ios_shell
    assert "ThoughtPinsOAuthProvider" in android_shell
    assert "NativeOAuthTokenProvider" in android_shell
    assert "oauthLogin(provider:" in android_shell
    assert "NativeUploadProvider" in android_shell
    assert "NativeUploadDestination" in android_shell
    assert "uploadSelectedFile(destination:" in android_shell
    assert "uploadFile(" in android_shell
    assert "NativeNotificationPermissionProvider" not in android_shell
    assert "registerDeviceForReview" not in android_shell
    assert "enableNotifications" not in android_shell
    assert "Legal and support" in android_shell
    assert "Privacy Policy" in android_shell
    assert "Account Deletion" in android_shell
    assert "AI Disclosure" in android_shell
    assert "legalUrl(configured:" in android_shell
    assert "acceptLegal" in android_shell
    assert "NativeExternalLinkOpener" in android_shell
    assert "openLegalLink" in android_shell
    activity_shell = (
        ROOT / shells["android"] / "src/main/kotlin/com/thoughtpins/app/ThoughtPinsActivity.kt"
    ).read_text(encoding="utf-8-sig")
    assert "AndroidExternalLinkOpener" in activity_shell
    assert "Intent.ACTION_VIEW" in activity_shell
    assert "externalLinkOpener = AndroidExternalLinkOpener(this)" in activity_shell
    assert "AndroidFileUploadProvider" in activity_shell
    assert "ActivityResultContracts.OpenDocument" in activity_shell
    assert "contentResolver.openInputStream" in activity_shell
    assert "Base64.encodeToString" in activity_shell
    assert "uploadProvider = AndroidFileUploadProvider" in activity_shell
    secure_store = (ROOT / shells["android"] / "src/main/kotlin/com/thoughtpins/app/AndroidSecureStores.kt").read_text(
        encoding="utf-8-sig"
    )
    assert "AndroidSecureSessionStore" in secure_store
    assert "AndroidEncryptedDraftStorage" in secure_store
    assert "KeyGenParameterSpec" in secure_store

    statuses = {flow["native_ui_status"] for flow in handoff["required_review_flows"]}
    assert any(status.startswith("shell_ready") for status in statuses)
    assert "core_ready_notifications_deferred_from_initial_review_target" in statuses


def test_native_core_clients_share_the_obsidian_import_contract() -> None:
    ios_client = (ROOT / "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/APIClient.swift").read_text(
        encoding="utf-8-sig"
    )
    ios_models = (ROOT / "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/Models.swift").read_text(
        encoding="utf-8-sig"
    )
    android_client = (
        ROOT / "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/ThoughtPinsApiClient.kt"
    ).read_text(encoding="utf-8-sig")
    android_models = (
        ROOT / "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/Models.kt"
    ).read_text(encoding="utf-8-sig")

    for client in (ios_client, android_client):
        assert "importObsidianVault" in client
        assert '"/v1/import/obsidian"' in client
        assert "contentBase64" in client
        assert "dryRun" in client
        # New clients must stage, preview, and explicitly apply large vaults.
        assert "importObsidianVaultResumable" in client
        assert "previewObsidianVaultResumable" in client
        assert "applyPreviewedVaultImport" in client
        assert "/v1/import/obsidian/uploads" in client
        assert "/chunks" in client
        assert "/preview" in client
        assert "/apply" in client
        assert "/cancel" in client
        assert "chunkSha256" in client
        assert "conflictPolicy" in client
    for models in (ios_models, android_models):
        assert "VaultImportSessionResponse" in models
        assert "VaultImportPreviewItem" in models
        assert "progressPercent" in models
        assert "cancelRequested" in models
        assert "VaultImportResponse" in models
        assert "journalJobsQueued" in models
        assert "libraryDocumentsImported" in models
