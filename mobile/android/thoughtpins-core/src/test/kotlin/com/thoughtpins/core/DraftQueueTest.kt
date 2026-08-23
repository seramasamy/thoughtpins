package com.thoughtpins.core

import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The draft queue is keyed by device, not by account.
 *
 * `syncQueuedDrafts` posts whatever it finds under whichever session is
 * current, so anything surviving sign-out or account deletion is journal text
 * belonging to one person that the next person to sign in uploads as their own.
 */
class DraftQueueTest {
    private class MemoryDraftStorage(var value: String? = null) : DraftStorage {
        override suspend fun read(): String? = value

        override suspend fun write(value: String) {
            this.value = value
        }
    }

    @Test
    fun `purge leaves nothing for the next account to sync`() = runBlocking {
        val storage = MemoryDraftStorage()
        val queue = DraftQueue(storage)
        queue.enqueue("A private note the first account never sent.")
        queue.enqueue("A second unsent note.")
        assertEquals(2, queue.list().size, "the drafts must exist before purge can be proven to remove them")

        queue.purge()

        assertTrue(queue.list().isEmpty(), "a departing account's drafts must not survive for the next session to upload")
        assertTrue(queue.pending().isEmpty(), "and they must not come back as pending work")
    }

    @Test
    fun `purge on an empty queue is not an error`() = runBlocking {
        val queue = DraftQueue(MemoryDraftStorage())

        // Sign-out runs on accounts that never drafted offline. Throwing here
        // would report a deletion failure for an account that was deleted.
        queue.purge()

        assertTrue(queue.list().isEmpty())
    }

    @Test
    fun `the queue is usable again after purge`() = runBlocking {
        val queue = DraftQueue(MemoryDraftStorage())
        queue.enqueue("First account note.")
        queue.purge()

        val draft = queue.enqueue("Second account note.")

        assertEquals(listOf("Second account note."), queue.list().map { it.text })
        assertEquals(DraftStatus.QUEUED, draft.status)
    }
}
