package com.thoughtpins.core

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.time.Instant
import java.util.UUID

interface DraftStorage {
    suspend fun read(): String?
    suspend fun write(value: String)
}

class DraftQueue(
    private val storage: DraftStorage,
    private val json: Json = Json { ignoreUnknownKeys = true },
) {
    suspend fun list(): List<CaptureDraft> {
        val raw = storage.read() ?: return emptyList()
        return json.decodeFromString<List<CaptureDraft>>(raw).sortedBy { it.createdAtUtc }
    }

    suspend fun enqueue(text: String): CaptureDraft {
        val normalized = text.trim()
        require(normalized.isNotEmpty() && normalized.length <= 50_000) { "Invalid journal text." }
        val now = Instant.now().toString()
        val draft = CaptureDraft(
            id = UUID.randomUUID().toString(),
            text = normalized,
            status = DraftStatus.QUEUED,
            createdAtUtc = now,
            updatedAtUtc = now,
            attemptCount = 0,
        )
        write(list() + draft)
        return draft
    }

    suspend fun pending(): List<CaptureDraft> =
        list().filter { it.status == DraftStatus.QUEUED || it.status == DraftStatus.FAILED }

    suspend fun update(draft: CaptureDraft) {
        write(list().filter { it.id != draft.id } + draft.copy(updatedAtUtc = Instant.now().toString()))
    }

    private suspend fun write(drafts: List<CaptureDraft>) {
        storage.write(json.encodeToString(drafts.filter { it.status != DraftStatus.SYNCED }.takeLast(250)))
    }
}
