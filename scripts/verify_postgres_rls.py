"""Verify PostgreSQL RLS tenant isolation using PostgreSQL.

Run this against a migrated staging database. `DATABASE_URL` is used for setup
and cleanup, and `RLS_VERIFY_DATABASE_URL` can point at the non-owner app role
that should be subject to RLS policies. If `RLS_VERIFY_DATABASE_URL` is omitted,
the configured `DATABASE_URL` is used for both roles.
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

from sqlalchemy import bindparam, create_engine, text

from thoughtpins.config import config
from thoughtpins.store import get_engine

RLS_EXEMPT_TABLES = {
    "auth_sessions": "Refresh-token lookup happens before tenant context is known; application code filters by opaque refresh-token hash and user state.",
    "oauth_credentials": "OAuth login resolves an exact hashed provider subject before tenant context exists; no credential-listing API is exposed.",
}

LIVE_RLS_TABLES = (
    "action_items",
    "api_idempotency_records",
    "app_devices",
    "audit_logs",
    "chat_conversations",
    "chat_messages",
    "document_chunks",
    "document_sources",
    "entities",
    "entity_mentions",
    "invite_requests",
    "event_participants",
    "events",
    "expenses",
    "ingestion_jobs",
    "llm_usage_events",
    "memories",
    "pending_chat_actions",
    "raw_entries",
    "relationships",
    "reports",
    "safety_reports",
    "vault_import_sessions",
    "voice_assets",
)

DELETE_ORDER = (
    "api_idempotency_records",
    "pending_chat_actions",
    "chat_messages",
    "chat_conversations",
    "document_chunks",
    "document_sources",
    "event_participants",
    "relationships",
    "memories",
    "entity_mentions",
    "action_items",
    "expenses",
    "events",
    "reports",
    "safety_reports",
    "vault_import_sessions",
    "voice_assets",
    "llm_usage_events",
    "invite_requests",
    "audit_logs",
    "app_devices",
    "ingestion_jobs",
    "raw_entries",
    "entities",
)


def _set_tenant(conn, user_id: str) -> None:
    conn.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": user_id},
    )


def _visible_ids(conn, table: str, row_ids: list[str]) -> list[str]:
    stmt = text(f"SELECT id FROM {table} WHERE id IN :row_ids ORDER BY id").bindparams(
        bindparam("row_ids", expanding=True)
    )
    return list(conn.execute(stmt, {"row_ids": row_ids}).scalars().all())


def _assert_visible(conn, table: str, row_ids: list[str], expected: list[str], tenant_label: str) -> bool:
    visible = _visible_ids(conn, table, row_ids)
    if visible != expected:
        print(f"{table} RLS verification failed for tenant {tenant_label}: expected {expected}, saw {visible}")
        return False
    return True


def _insert_fixture_rows(conn, ids: dict[str, tuple[str, str]], user_a: str, user_b: str, suffix: str) -> None:
    entry_a, entry_b = ids["raw_entries"]
    entity_a1, entity_b1 = ids["entities_primary"]
    entity_a2, entity_b2 = ids["entities_secondary"]
    event_a, event_b = ids["events"]
    doc_a, doc_b = ids["document_sources"]
    conv_a, conv_b = ids["chat_conversations"]
    job_a, job_b = ids["ingestion_jobs"]
    memory_a, memory_b = ids["memories"]

    conn.execute(
        text(
            """
            INSERT INTO users (id, display_name, api_key, is_active, is_admin, auth_method)
            VALUES
              (:user_a, 'RLS A', :key_a, true, false, 'api_key'),
              (:user_b, 'RLS B', :key_b, true, false, 'api_key')
            """
        ),
        {
            "user_a": user_a,
            "user_b": user_b,
            "key_a": f"rls_a_key_{suffix}",
            "key_b": f"rls_b_key_{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO raw_entries (id, user_id, raw_text, content_hash, processed_status)
            VALUES
              (:entry_a, :user_a, 'A tenant entry', :hash_a, 'completed'),
              (:entry_b, :user_b, 'B tenant entry', :hash_b, 'completed')
            """
        ),
        {
            "entry_a": entry_a,
            "entry_b": entry_b,
            "user_a": user_a,
            "user_b": user_b,
            "hash_a": f"rlsa{suffix}",
            "hash_b": f"rlsb{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO ingestion_jobs (id, user_id, status, source, raw_text, entry_id)
            VALUES
              (:job_a, :user_a, 'completed', 'rls', 'A job', :entry_a),
              (:job_b, :user_b, 'completed', 'rls', 'B job', :entry_b)
            """
        ),
        {"job_a": job_a, "job_b": job_b, "user_a": user_a, "user_b": user_b, "entry_a": entry_a, "entry_b": entry_b},
    )
    conn.execute(
        text(
            """
            INSERT INTO entities (id, user_id, type, canonical_name)
            VALUES
              (:entity_a1, :user_a, 'person', 'RLS Person A'),
              (:entity_a2, :user_a, 'project', 'RLS Project A'),
              (:entity_b1, :user_b, 'person', 'RLS Person B'),
              (:entity_b2, :user_b, 'project', 'RLS Project B')
            """
        ),
        {
            "entity_a1": entity_a1,
            "entity_a2": entity_a2,
            "entity_b1": entity_b1,
            "entity_b2": entity_b2,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO entity_mentions (id, user_id, raw_entry_id, entity_id, surface_text)
            VALUES
              (:mention_a, :user_a, :entry_a, :entity_a1, 'RLS Person A'),
              (:mention_b, :user_b, :entry_b, :entity_b1, 'RLS Person B')
            """
        ),
        {
            "mention_a": ids["entity_mentions"][0],
            "mention_b": ids["entity_mentions"][1],
            "user_a": user_a,
            "user_b": user_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
            "entity_a1": entity_a1,
            "entity_b1": entity_b1,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO memories (id, user_id, raw_entry_id, memory_type, text)
            VALUES
              (:memory_a, :user_a, :entry_a, 'fact', 'A memory'),
              (:memory_b, :user_b, :entry_b, 'fact', 'B memory')
            """
        ),
        {
            "memory_a": memory_a,
            "memory_b": memory_b,
            "user_a": user_a,
            "user_b": user_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO relationships
              (id, user_id, source_entity_id, target_entity_id, relation_type, raw_entry_id, memory_id)
            VALUES
              (:rel_a, :user_a, :entity_a1, :entity_a2, 'works_on', :entry_a, :memory_a),
              (:rel_b, :user_b, :entity_b1, :entity_b2, 'works_on', :entry_b, :memory_b)
            """
        ),
        {
            "rel_a": ids["relationships"][0],
            "rel_b": ids["relationships"][1],
            "user_a": user_a,
            "user_b": user_b,
            "entity_a1": entity_a1,
            "entity_a2": entity_a2,
            "entity_b1": entity_b1,
            "entity_b2": entity_b2,
            "entry_a": entry_a,
            "entry_b": entry_b,
            "memory_a": memory_a,
            "memory_b": memory_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO events (id, user_id, name, event_type, place_entity_id, source_raw_entry_id)
            VALUES
              (:event_a, :user_a, 'A event', 'meeting', :entity_a2, :entry_a),
              (:event_b, :user_b, 'B event', 'meeting', :entity_b2, :entry_b)
            """
        ),
        {
            "event_a": event_a,
            "event_b": event_b,
            "user_a": user_a,
            "user_b": user_b,
            "entity_a2": entity_a2,
            "entity_b2": entity_b2,
            "entry_a": entry_a,
            "entry_b": entry_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO event_participants (id, user_id, event_id, entity_id, role)
            VALUES
              (:participant_a, :user_a, :event_a, :entity_a1, 'attendee'),
              (:participant_b, :user_b, :event_b, :entity_b1, 'attendee')
            """
        ),
        {
            "participant_a": ids["event_participants"][0],
            "participant_b": ids["event_participants"][1],
            "user_a": user_a,
            "user_b": user_b,
            "event_a": event_a,
            "event_b": event_b,
            "entity_a1": entity_a1,
            "entity_b1": entity_b1,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO action_items (id, user_id, raw_entry_id, description, status)
            VALUES
              (:action_a, :user_a, :entry_a, 'A action', 'open'),
              (:action_b, :user_b, :entry_b, 'B action', 'open')
            """
        ),
        {
            "action_a": ids["action_items"][0],
            "action_b": ids["action_items"][1],
            "user_a": user_a,
            "user_b": user_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO expenses (id, user_id, raw_entry_id, amount, currency, reason)
            VALUES
              (:expense_a, :user_a, :entry_a, 12.5, 'USD', 'A expense'),
              (:expense_b, :user_b, :entry_b, 22.5, 'USD', 'B expense')
            """
        ),
        {
            "expense_a": ids["expenses"][0],
            "expense_b": ids["expenses"][1],
            "user_a": user_a,
            "user_b": user_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO reports (id, user_id, query, report_type)
            VALUES
              (:report_a, :user_a, 'A report', 'rls'),
              (:report_b, :user_b, 'B report', 'rls')
            """
        ),
        {"report_a": ids["reports"][0], "report_b": ids["reports"][1], "user_a": user_a, "user_b": user_b},
    )
    conn.execute(
        text(
            """
            INSERT INTO safety_reports (id, user_id, category, source, target_type, summary, status, metadata_json)
            VALUES
              (:safety_a, :user_a, 'unsafe_ai_output', 'api', 'general', 'A safety report', 'received', '{}'),
              (:safety_b, :user_b, 'privacy_concern', 'api', 'general', 'B safety report', 'received', '{}')
            """
        ),
        {
            "safety_a": ids["safety_reports"][0],
            "safety_b": ids["safety_reports"][1],
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO vault_import_sessions (
                id, user_id, status, filename, mode, conflict_policy, expected_bytes, received_bytes,
                storage_key, progress_current, progress_total, progress_stage, cancel_requested,
                created_at_utc, updated_at_utc, expires_at_utc
            )
            VALUES
              (:transfer_a, :user_a, 'uploading', 'a.zip', 'auto', 'skip', 10, 0,
               :storage_a, 0, 10, 'uploading', false, NOW(), NOW(), NOW() + INTERVAL '1 day'),
              (:transfer_b, :user_b, 'uploading', 'b.zip', 'auto', 'skip', 10, 0,
               :storage_b, 0, 10, 'uploading', false, NOW(), NOW(), NOW() + INTERVAL '1 day')
            """
        ),
        {
            "transfer_a": ids["vault_import_sessions"][0],
            "transfer_b": ids["vault_import_sessions"][1],
            "user_a": user_a,
            "user_b": user_b,
            "storage_a": f"rls-transfer-a-{suffix}",
            "storage_b": f"rls-transfer-b-{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO voice_assets (
                id, user_id, raw_entry_id, storage_ref, original_filename, media_type, container,
                byte_size_original, byte_size_encrypted, storage_codec, content_fingerprint, transcript_chars,
                transcription_language, transcription_mode, consent_version, retention_purpose,
                derived_data_status, created_at_utc
            )
            VALUES
              (:voice_a, :user_a, :raw_a, :ref_a, 'a.m4a', 'audio/mp4', 'm4a', 10, 20,
               'fernet+zlib-v1', :fingerprint_a, 12,
               'en', 'local', 'rls', 'personal_voice_features', 'not_created', CURRENT_TIMESTAMP),
              (:voice_b, :user_b, :raw_b, :ref_b, 'b.m4a', 'audio/mp4', 'm4a', 10, 20,
               'fernet+zlib-v1', :fingerprint_b, 12,
               'en', 'local', 'rls', 'personal_voice_features', 'not_created', CURRENT_TIMESTAMP)
            """
        ),
        {
            "voice_a": ids["voice_assets"][0],
            "voice_b": ids["voice_assets"][1],
            "user_a": user_a,
            "user_b": user_b,
            "raw_a": ids["raw_entries"][0],
            "raw_b": ids["raw_entries"][1],
            "ref_a": f"rls/{ids['voice_assets'][0]}.enc",
            "ref_b": f"rls/{ids['voice_assets'][1]}.enc",
            "fingerprint_a": "a" * 64,
            "fingerprint_b": "b" * 64,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO audit_logs (id, user_id, action, metadata_json)
            VALUES
              (:audit_a, :user_a, 'rls.verify', '{}'),
              (:audit_b, :user_b, 'rls.verify', '{}')
            """
        ),
        {"audit_a": ids["audit_logs"][0], "audit_b": ids["audit_logs"][1], "user_a": user_a, "user_b": user_b},
    )
    conn.execute(
        text(
            """
            INSERT INTO invite_requests (
                id, user_id, note, status, created_at_utc, updated_at_utc
            )
            VALUES
              (:invreq_a, :user_a, 'rls probe', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              (:invreq_b, :user_b, 'rls probe', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "invreq_a": ids["invite_requests"][0],
            "invreq_b": ids["invite_requests"][1],
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO llm_usage_events (
                id, user_id, created_at_utc, provider, model, operation,
                prompt_tokens, completion_tokens, total_tokens, cost_usd
            )
            VALUES
              (:usage_a, :user_a, CURRENT_TIMESTAMP, 'rls', 'rls-model', 'chat', 10, 5, 15, 0.001),
              (:usage_b, :user_b, CURRENT_TIMESTAMP, 'rls', 'rls-model', 'chat', 10, 5, 15, 0.001)
            """
        ),
        {
            "usage_a": ids["llm_usage_events"][0],
            "usage_b": ids["llm_usage_events"][1],
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO api_idempotency_records
              (id, user_id, scope, idempotency_key, request_hash, status, created_at_utc, expires_at_utc)
            VALUES
              (:idem_a, :user_a, 'POST:/v1/entries', :key_a, :hash_a, 'in_progress', NOW(), NOW() + INTERVAL '1 day'),
              (:idem_b, :user_b, 'POST:/v1/entries', :key_b, :hash_b, 'in_progress', NOW(), NOW() + INTERVAL '1 day')
            """
        ),
        {
            "idem_a": ids["api_idempotency_records"][0],
            "idem_b": ids["api_idempotency_records"][1],
            "user_a": user_a,
            "user_b": user_b,
            "key_a": f"idem-a-{suffix}",
            "key_b": f"idem-b-{suffix}",
            "hash_a": f"hash-a-{suffix}",
            "hash_b": f"hash-b-{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO app_devices (id, user_id, installation_id, platform, metadata_json)
            VALUES
              (:device_a, :user_a, :install_a, 'web', '{}'),
              (:device_b, :user_b, :install_b, 'web', '{}')
            """
        ),
        {
            "device_a": ids["app_devices"][0],
            "device_b": ids["app_devices"][1],
            "user_a": user_a,
            "user_b": user_b,
            "install_a": f"install_a_{suffix}",
            "install_b": f"install_b_{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO document_sources
              (id, user_id, raw_entry_id, source_type, title, content_hash, raw_text, status)
            VALUES
              (:doc_a, :user_a, :entry_a, 'text', 'Source A', :source_hash_a, 'A source', 'processed'),
              (:doc_b, :user_b, :entry_b, 'text', 'Source B', :source_hash_b, 'B source', 'processed')
            """
        ),
        {
            "doc_a": doc_a,
            "doc_b": doc_b,
            "user_a": user_a,
            "user_b": user_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
            "source_hash_a": f"rls_source_a_hash_{suffix}",
            "source_hash_b": f"rls_source_b_hash_{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO document_chunks (id, user_id, document_id, chunk_index, text)
            VALUES
              (:chunk_a, :user_a, :doc_a, 0, 'A chunk'),
              (:chunk_b, :user_b, :doc_b, 0, 'B chunk')
            """
        ),
        {
            "chunk_a": ids["document_chunks"][0],
            "chunk_b": ids["document_chunks"][1],
            "user_a": user_a,
            "user_b": user_b,
            "doc_a": doc_a,
            "doc_b": doc_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO chat_conversations
              (id, user_id, conversation_key, surface, title, created_at_utc, updated_at_utc)
            VALUES
              (:conv_a, :user_a, :key_a, 'web', 'RLS chat A', NOW(), NOW()),
              (:conv_b, :user_b, :key_b, 'web', 'RLS chat B', NOW(), NOW())
            """
        ),
        {
            "conv_a": conv_a,
            "conv_b": conv_b,
            "user_a": user_a,
            "user_b": user_b,
            "key_a": f"web:rls-a-{suffix}",
            "key_b": f"web:rls-b-{suffix}",
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO chat_messages
              (id, user_id, conversation_id, role, text, route_type, status, created_at_utc)
            VALUES
              (:message_a, :user_a, :conv_a, 'user', 'A chat', 'chat', 'received', NOW()),
              (:message_b, :user_b, :conv_b, 'user', 'B chat', 'chat', 'received', NOW())
            """
        ),
        {
            "message_a": ids["chat_messages"][0],
            "message_b": ids["chat_messages"][1],
            "user_a": user_a,
            "user_b": user_b,
            "conv_a": conv_a,
            "conv_b": conv_b,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO pending_chat_actions
              (id, user_id, conversation_id, action, prompt, status, created_at_utc, expires_at_utc)
            VALUES
              (:pending_a, :user_a, :conv_a, 'undo', 'Confirm undo', 'pending', NOW(), NOW() + INTERVAL '5 minutes'),
              (:pending_b, :user_b, :conv_b, 'undo', 'Confirm undo', 'pending', NOW(), NOW() + INTERVAL '5 minutes')
            """
        ),
        {
            "pending_a": ids["pending_chat_actions"][0],
            "pending_b": ids["pending_chat_actions"][1],
            "user_a": user_a,
            "user_b": user_b,
            "conv_a": conv_a,
            "conv_b": conv_b,
        },
    )


def _cleanup_fixture_rows(conn, ids: dict[str, tuple[str, str]], user_ids: list[str]) -> None:
    for table in DELETE_ORDER:
        table_ids: list[str] = []
        if table == "entities":
            table_ids.extend(ids["entities_primary"])
            table_ids.extend(ids["entities_secondary"])
        else:
            table_ids.extend(ids[table])
        stmt = text(f"DELETE FROM {table} WHERE id IN :row_ids").bindparams(bindparam("row_ids", expanding=True))
        conn.execute(stmt, {"row_ids": table_ids})
    delete_users = text("DELETE FROM users WHERE id IN :user_ids").bindparams(bindparam("user_ids", expanding=True))
    conn.execute(delete_users, {"user_ids": user_ids})


def main() -> int:
    if not config.database_url_sync().startswith("postgresql"):
        print("RLS verification requires PostgreSQL.")
        return 1

    verify_url = os.getenv("RLS_VERIFY_DATABASE_URL", "").strip() or config.database_url_sync()
    if not verify_url.startswith("postgresql"):
        print("RLS_VERIFY_DATABASE_URL must point at PostgreSQL when set.")
        return 1

    suffix = uuid4().hex[:8]
    user_a = f"rls_user_a_{suffix}"
    user_b = f"rls_user_b_{suffix}"
    ids = {
        "action_items": (f"act_a_{suffix}", f"act_b_{suffix}"),
        "api_idempotency_records": (f"ide_a_{suffix}", f"ide_b_{suffix}"),
        "app_devices": (f"dev_a_{suffix}", f"dev_b_{suffix}"),
        "audit_logs": (f"aud_a_{suffix}", f"aud_b_{suffix}"),
        "chat_conversations": (f"conv_a_{suffix}", f"conv_b_{suffix}"),
        "chat_messages": (f"msg_a_{suffix}", f"msg_b_{suffix}"),
        "document_chunks": (f"chk_a_{suffix}", f"chk_b_{suffix}"),
        "document_sources": (f"doc_a_{suffix}", f"doc_b_{suffix}"),
        "entities_primary": (f"ent1_a_{suffix}", f"ent1_b_{suffix}"),
        "entities_secondary": (f"ent2_a_{suffix}", f"ent2_b_{suffix}"),
        "entity_mentions": (f"men_a_{suffix}", f"men_b_{suffix}"),
        "event_participants": (f"par_a_{suffix}", f"par_b_{suffix}"),
        "events": (f"evt_a_{suffix}", f"evt_b_{suffix}"),
        "expenses": (f"exp_a_{suffix}", f"exp_b_{suffix}"),
        "ingestion_jobs": (f"job_a_{suffix}", f"job_b_{suffix}"),
        "memories": (f"mem_a_{suffix}", f"mem_b_{suffix}"),
        "pending_chat_actions": (f"pnd_a_{suffix}", f"pnd_b_{suffix}"),
        "raw_entries": (f"raw_a_{suffix}", f"raw_b_{suffix}"),
        "relationships": (f"rel_a_{suffix}", f"rel_b_{suffix}"),
        "reports": (f"rep_a_{suffix}", f"rep_b_{suffix}"),
        "safety_reports": (f"saf_a_{suffix}", f"saf_b_{suffix}"),
        "vault_import_sessions": (f"vlt_a_{suffix}", f"vlt_b_{suffix}"),
        "voice_assets": (f"voc_a_{suffix}", f"voc_b_{suffix}"),
        "llm_usage_events": (f"usg_a_{suffix}", f"usg_b_{suffix}"),
        "invite_requests": (f"inv_a_{suffix}", f"inv_b_{suffix}"),
    }

    admin_engine = get_engine()
    verify_engine = create_engine(verify_url, future=True, pool_pre_ping=True)

    try:
        with admin_engine.begin() as conn:
            _insert_fixture_rows(conn, ids, user_a, user_b, suffix)

        with verify_engine.begin() as conn:
            current_user = conn.execute(text("SELECT current_user")).scalar()
            table_owner = conn.execute(
                text(
                    """
                    SELECT tableowner
                    FROM pg_tables
                    WHERE schemaname = 'public' AND tablename = 'raw_entries'
                    """
                )
            ).scalar()
            if current_user == table_owner:
                print(
                    "Warning: verifier role owns raw_entries; use RLS_VERIFY_DATABASE_URL "
                    "with a non-owner app role for a production-faithful check."
                )

            table_ids = {table: list(pair) for table, pair in ids.items() if table in LIVE_RLS_TABLES}
            table_ids["entities"] = [*ids["entities_primary"], *ids["entities_secondary"]]
            expected_a = {table: [pair[0]] for table, pair in table_ids.items()}
            expected_b = {table: [pair[-1]] for table, pair in table_ids.items()}
            expected_a["entities"] = [ids["entities_primary"][0], ids["entities_secondary"][0]]
            expected_b["entities"] = [ids["entities_primary"][1], ids["entities_secondary"][1]]

            _set_tenant(conn, user_a)
            for table in LIVE_RLS_TABLES:
                if not _assert_visible(conn, table, table_ids[table], expected_a[table], "A"):
                    return 1

            _set_tenant(conn, user_b)
            for table in LIVE_RLS_TABLES:
                if not _assert_visible(conn, table, table_ids[table], expected_b[table], "B"):
                    return 1

        print("PostgreSQL RLS verification passed for all user-owned RLS tables.")
        return 0
    finally:
        verify_engine.dispose()
        with admin_engine.begin() as conn:
            _cleanup_fixture_rows(conn, ids, [user_a, user_b])


if __name__ == "__main__":
    sys.exit(main())
