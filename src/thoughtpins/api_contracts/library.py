"""Library, upload, and portable-vault HTTP contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LibraryIngestRequest(BaseModel):
    text: str | None = Field(default=None, max_length=200_000)
    url: str | None = Field(default=None, max_length=4_000)
    title: str | None = Field(default=None, max_length=512)
    author: str | None = Field(default=None, max_length=255)
    source_type: str = Field(default="text", max_length=32)
    user_importance: int | None = Field(default=None, ge=1, le=5)

    @field_validator("text", "url", "title", "author", mode="before")
    @classmethod
    def strip_optional(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class LibraryIngestResponse(BaseModel):
    job_id: str | None = None
    document_id: str
    raw_entry_id: str
    title: str
    source_type: str
    status: str
    chunks: int
    memories: int
    source_url: str | None = None
    duplicate: bool = False
    error: str | None = None
    access_method: str | None = None
    rights_basis: str | None = None
    paywall_detected: bool = False
    user_importance: int | None = Field(default=None, ge=1, le=5)


class UploadIngestRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., max_length=36_000_000)
    media_type: str | None = Field(default=None, max_length=128)
    destination: Literal["auto", "journal", "library"] = "auto"
    caption: str | None = Field(default=None, max_length=10_000)
    title: str | None = Field(default=None, max_length=512)
    source_type: str | None = Field(default=None, max_length=32)
    surface: str = Field(default="upload", max_length=32)
    conversation_id: str = Field(default="uploads", max_length=96)

    @field_validator(
        "filename", "media_type", "caption", "title", "source_type", "surface", "conversation_id", mode="before"
    )
    @classmethod
    def strip_upload_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class UploadIngestResponse(BaseModel):
    status: str
    route_type: str
    filename: str
    media_kind: str
    destination: str
    extraction_status: str
    extracted_chars: int = 0
    attachment_saved: bool = False
    attachment_ref: str | None = None
    voice_asset_id: str | None = None
    title: str | None = None
    entry_id: str | None = None
    job_id: str | None = None
    document_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VaultImportRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255, examples=["my-obsidian-vault.zip"])
    content_base64: str = Field(..., max_length=36_000_000)
    mode: Literal["auto", "all_library", "all_journal"] = Field(
        default="auto",
        pattern="^(auto|all_library|all_journal)$",
        description="Auto detects journals; overrides can treat imported notes as library or journal content.",
    )
    conflict_policy: Literal["skip", "append"] = Field(
        default="skip",
        description="Skip changed paths or append their edited content as a new revision.",
    )
    dry_run: bool = Field(default=False, description="Inspect and classify the vault without writing user data.")

    @field_validator("filename", mode="before")
    @classmethod
    def strip_vault_filename(cls, value):
        return value.strip() if isinstance(value, str) else value


class VaultImportPreviewItem(BaseModel):
    path: str
    title: str
    kind: Literal["journal", "library"]
    state: Literal["new", "unchanged", "changed"]
    action: Literal["import", "skip_duplicate", "skip_conflict", "append_revision"]


class VaultImportResponse(BaseModel):
    status: str
    format: str
    mode: str
    thoughtpins_export: bool
    dry_run: bool
    archive_sha256: str
    files_discovered: int
    notes_discovered: int
    attachments_skipped: int
    structural_files_skipped: int
    canvases_discovered: int
    canvas_documents_imported: int
    journal_notes: int
    library_notes: int
    journal_jobs_queued: int
    library_documents_imported: int
    new_notes: int
    changed_notes: int
    unchanged_notes: int
    conflicts: int
    duplicates: int
    skipped: int
    imported: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    preview_items: list[VaultImportPreviewItem] = Field(default_factory=list)


class VaultUploadCreateRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255, examples=["my-obsidian-vault.zip"])
    expected_bytes: int = Field(..., ge=1, le=100 * 1024 * 1024)
    archive_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    mode: Literal["auto", "all_library", "all_journal"] = "auto"
    conflict_policy: Literal["skip", "append"] = "skip"

    @field_validator("filename", mode="before")
    @classmethod
    def strip_upload_filename(cls, value):
        return value.strip() if isinstance(value, str) else value


class VaultUploadChunkRequest(BaseModel):
    offset: int = Field(..., ge=0)
    content_base64: str = Field(..., min_length=1, max_length=710_000)
    chunk_sha256: str = Field(..., pattern="^[0-9a-f]{64}$")


class VaultImportOperationRequest(BaseModel):
    conflict_policy: Literal["skip", "append"] | None = None


class VaultImportSessionResponse(BaseModel):
    id: str
    status: str
    operation: Literal["preview", "apply"] | None = None
    filename: str
    mode: Literal["auto", "all_library", "all_journal"]
    conflict_policy: Literal["skip", "append"]
    expected_bytes: int
    received_bytes: int
    archive_sha256: str | None = None
    progress_current: int
    progress_total: int
    progress_percent: float
    progress_stage: str
    cancel_requested: bool
    result: VaultImportResponse | None = None
    error: str | None = None
    created_at_utc: str | None = None
    updated_at_utc: str | None = None
    finished_at_utc: str | None = None
    expires_at_utc: str | None = None
