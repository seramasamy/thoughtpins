"""Source-library, upload, and portable-vault routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from starlette.concurrency import run_in_threadpool

from thoughtpins.api_contracts import (
    LibraryIngestRequest,
    LibraryIngestResponse,
    UploadIngestRequest,
    UploadIngestResponse,
    VaultImportOperationRequest,
    VaultImportRequest,
    VaultImportResponse,
    VaultImportSessionResponse,
    VaultUploadChunkRequest,
    VaultUploadCreateRequest,
)
from thoughtpins.api_contracts.common import INTERNAL_ERROR_MESSAGE
from thoughtpins.api_memory_cards import LibrarySourceResponse, source_response
from thoughtpins.audit import record_audit_event
from thoughtpins.library import find_document, ingest_document_text, ingest_url, list_documents
from thoughtpins.store import get_session
from thoughtpins.uploads import decode_upload_content, ingest_upload
from thoughtpins.vault.importer import MAX_ARCHIVE_BYTES, import_obsidian_vault
from thoughtpins.vault.transfers import (
    VaultTransferStateError,
    append_vault_import_chunk,
    cancel_vault_import_session,
    create_vault_import_session,
    get_vault_import_session,
    queue_vault_import_operation,
    vault_import_session_payload,
)


def create_library_router(*, current_user_dependency: Callable[..., str]) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/library", response_model=LibraryIngestResponse)
    async def create_library_source(
        payload: LibraryIngestRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> LibraryIngestResponse:
        return await run_in_threadpool(_create_library_source_sync, payload, user_id)

    @router.post("/v1/uploads", response_model=UploadIngestResponse)
    async def create_upload(
        payload: UploadIngestRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> UploadIngestResponse:
        try:
            content = decode_upload_content(payload.content_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await run_in_threadpool(_create_upload_sync, payload, user_id, content)

    @router.post(
        "/v1/import/obsidian",
        response_model=VaultImportResponse,
        summary="Import an Obsidian vault ZIP",
        description=(
            "Securely scans a user-provided Obsidian ZIP. Journal notes enter the normal memory extraction queue; "
            "other Markdown notes become recallable library sources. Thought Pins exports are recognized and "
            "derived index/entity notes are not duplicated."
        ),
    )
    async def import_obsidian(
        payload: VaultImportRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportResponse:
        try:
            content = decode_upload_content(payload.content_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if len(content) > MAX_ARCHIVE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Vault archive exceeds the {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB compressed limit",
            )
        return await run_in_threadpool(_import_obsidian_vault_sync, payload, user_id, content)

    @router.post(
        "/v1/import/obsidian/uploads",
        response_model=VaultImportSessionResponse,
        status_code=201,
        summary="Begin a resumable Obsidian vault upload",
    )
    async def create_obsidian_upload(
        payload: VaultUploadCreateRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        return await run_in_threadpool(_create_vault_upload_sync, payload, user_id)

    @router.put(
        "/v1/import/obsidian/uploads/{transfer_id}/chunks",
        response_model=VaultImportSessionResponse,
        summary="Append an integrity-checked vault upload chunk",
    )
    async def append_obsidian_upload_chunk(
        transfer_id: str,
        payload: VaultUploadChunkRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        try:
            content = decode_upload_content(payload.content_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await run_in_threadpool(_append_vault_upload_chunk_sync, transfer_id, payload, content, user_id)

    @router.get(
        "/v1/import/obsidian/uploads/{transfer_id}",
        response_model=VaultImportSessionResponse,
        summary="Read vault upload or import progress",
    )
    async def get_obsidian_upload(
        transfer_id: str,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        return await run_in_threadpool(_get_vault_upload_sync, transfer_id, user_id)

    @router.post(
        "/v1/import/obsidian/uploads/{transfer_id}/preview",
        response_model=VaultImportSessionResponse,
        status_code=202,
        summary="Queue a read-only vault import preview",
    )
    async def preview_obsidian_upload(
        transfer_id: str,
        payload: VaultImportOperationRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        return await run_in_threadpool(_queue_vault_operation_sync, transfer_id, "preview", payload, user_id)

    @router.post(
        "/v1/import/obsidian/uploads/{transfer_id}/apply",
        response_model=VaultImportSessionResponse,
        status_code=202,
        summary="Apply a reviewed vault import",
    )
    async def apply_obsidian_upload(
        transfer_id: str,
        payload: VaultImportOperationRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        return await run_in_threadpool(_queue_vault_operation_sync, transfer_id, "apply", payload, user_id)

    @router.post(
        "/v1/import/obsidian/uploads/{transfer_id}/cancel",
        response_model=VaultImportSessionResponse,
        summary="Cancel and remove a staged vault import",
    )
    async def cancel_obsidian_upload(
        transfer_id: str,
        user_id: str = Depends(current_user_dependency),
    ) -> VaultImportSessionResponse:
        return await run_in_threadpool(_cancel_vault_upload_sync, transfer_id, user_id)

    @router.get("/v1/library", response_model=list[LibrarySourceResponse])
    async def get_library_sources(
        limit: int = Query(20, ge=1, le=100),
        user_id: str = Depends(current_user_dependency),
    ) -> list[LibrarySourceResponse]:
        session = get_session()
        try:
            return [source_response(doc) for doc in list_documents(session, user_id, limit=limit)]
        finally:
            session.close()

    @router.get("/v1/library/{source_ref}", response_model=LibrarySourceResponse)
    async def get_library_source(
        source_ref: str,
        user_id: str = Depends(current_user_dependency),
    ) -> LibrarySourceResponse:
        session = get_session()
        try:
            document = find_document(session, user_id, source_ref)
            if not document:
                raise HTTPException(status_code=404, detail="Source not found")
            return source_response(document, include_summary=True)
        finally:
            session.close()

    return router


def _create_library_source_sync(payload: LibraryIngestRequest, user_id: str) -> LibraryIngestResponse:
    if not payload.url and not payload.text:
        raise HTTPException(status_code=400, detail="Provide url or text")

    session = get_session()
    try:
        if payload.url:
            result = ingest_url(
                session,
                payload.url,
                user_id=user_id,
                note=payload.text or "",
                defer_vector_index=True,
                user_importance=payload.user_importance,
            )
        else:
            result = ingest_document_text(
                session,
                payload.text or "",
                user_id=user_id,
                source_type=payload.source_type or "text",
                title=payload.title or "",
                author=payload.author,
                defer_vector_index=True,
                user_importance=payload.user_importance,
            )
        record_audit_event(
            session,
            user_id=user_id,
            action="library.created",
            metadata={"document_id": result.document_id, "source_type": result.source_type},
        )
        return LibraryIngestResponse(**result.__dict__)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Library ingest failed")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from exc
    finally:
        session.close()


def _create_upload_sync(payload: UploadIngestRequest, user_id: str, content: bytes) -> UploadIngestResponse:
    session = get_session()
    try:
        outcome = ingest_upload(
            session,
            user_id=user_id,
            filename=payload.filename,
            content=content,
            media_type=payload.media_type or "",
            destination=payload.destination,
            caption=payload.caption or "",
            title=payload.title or "",
            source_type=payload.source_type or "",
            surface=payload.surface or "upload",
            conversation_id=payload.conversation_id or "uploads",
        )
        record_audit_event(
            session,
            user_id=user_id,
            action="voice.note.processed" if outcome.media_kind == "audio" else "upload.ingested",
            metadata={
                "status": outcome.status,
                "route_type": outcome.route_type,
                "media_kind": outcome.media_kind,
                "destination": outcome.destination,
                "document_id": outcome.document_id,
                "entry_id": outcome.entry_id,
                "voice_retained": bool(outcome.voice_asset_id),
                "voice_asset_id": outcome.voice_asset_id,
                "extraction_status": outcome.extraction_status,
            },
        )
        return UploadIngestResponse(**outcome.__dict__)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Upload ingest failed")
        raise HTTPException(status_code=500, detail="Upload processing failed") from exc
    finally:
        session.close()


def _import_obsidian_vault_sync(
    payload: VaultImportRequest,
    user_id: str,
    content: bytes,
) -> VaultImportResponse:
    session = get_session()
    try:
        result = import_obsidian_vault(
            session,
            user_id=user_id,
            filename=payload.filename,
            archive=content,
            mode=payload.mode,
            conflict_policy=payload.conflict_policy,
            dry_run=payload.dry_run,
        )
        record_audit_event(
            session,
            user_id=user_id,
            action="vault.imported" if not payload.dry_run else "vault.import.previewed",
            metadata={
                "format": result.format,
                "mode": result.mode,
                "notes_discovered": result.notes_discovered,
                "canvases_discovered": result.canvases_discovered,
                "canvas_documents_imported": result.canvas_documents_imported,
                "structural_files_skipped": result.structural_files_skipped,
                "journal_jobs_queued": result.journal_jobs_queued,
                "library_documents_imported": result.library_documents_imported,
                "duplicates": result.duplicates,
                "errors": len(result.errors),
            },
        )
        return VaultImportResponse(**result.as_dict())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Obsidian vault import failed")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from exc
    finally:
        session.close()


def _create_vault_upload_sync(payload: VaultUploadCreateRequest, user_id: str) -> VaultImportSessionResponse:
    session = get_session()
    try:
        transfer = create_vault_import_session(
            session,
            user_id=user_id,
            filename=payload.filename,
            expected_bytes=payload.expected_bytes,
            archive_sha256=payload.archive_sha256,
            mode=payload.mode,
            conflict_policy=payload.conflict_policy,
        )
        record_audit_event(
            session,
            user_id=user_id,
            action="vault.upload.created",
            metadata={"transfer_id": transfer.id, "expected_bytes": transfer.expected_bytes},
        )
        return VaultImportSessionResponse(**vault_import_session_payload(transfer))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


def _append_vault_upload_chunk_sync(
    transfer_id: str,
    payload: VaultUploadChunkRequest,
    content: bytes,
    user_id: str,
) -> VaultImportSessionResponse:
    session = get_session()
    try:
        transfer = append_vault_import_chunk(
            session,
            user_id=user_id,
            transfer_id=transfer_id,
            offset=payload.offset,
            content=content,
            chunk_sha256=payload.chunk_sha256,
        )
        return VaultImportSessionResponse(**vault_import_session_payload(transfer))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VaultTransferStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()


def _get_vault_upload_sync(transfer_id: str, user_id: str) -> VaultImportSessionResponse:
    session = get_session()
    try:
        transfer = get_vault_import_session(session, user_id=user_id, transfer_id=transfer_id)
        if not transfer:
            raise HTTPException(status_code=404, detail="Vault import session not found")
        return VaultImportSessionResponse(**vault_import_session_payload(transfer))
    finally:
        session.close()


def _queue_vault_operation_sync(
    transfer_id: str,
    operation: Literal["preview", "apply"],
    payload: VaultImportOperationRequest,
    user_id: str,
) -> VaultImportSessionResponse:
    session = get_session()
    try:
        transfer = queue_vault_import_operation(
            session,
            user_id=user_id,
            transfer_id=transfer_id,
            operation=operation,
            conflict_policy=payload.conflict_policy,
        )
        record_audit_event(
            session,
            user_id=user_id,
            action=f"vault.import.{operation}.queued",
            metadata={"transfer_id": transfer.id, "conflict_policy": transfer.conflict_policy},
        )
        return VaultImportSessionResponse(**vault_import_session_payload(transfer))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VaultTransferStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        session.close()


def _cancel_vault_upload_sync(transfer_id: str, user_id: str) -> VaultImportSessionResponse:
    session = get_session()
    try:
        transfer = cancel_vault_import_session(session, user_id=user_id, transfer_id=transfer_id)
        record_audit_event(
            session,
            user_id=user_id,
            action="vault.import.canceled",
            metadata={"transfer_id": transfer.id},
        )
        return VaultImportSessionResponse(**vault_import_session_payload(transfer))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        session.close()
