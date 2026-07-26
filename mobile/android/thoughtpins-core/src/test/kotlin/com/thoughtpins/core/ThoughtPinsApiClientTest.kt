package com.thoughtpins.core

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class ThoughtPinsApiClientTest {
    @Test
    fun `client config tolerates future fields and preserves review switches`() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""
                {
                  "app_name": "Thought Pins",
                  "api_version": "v1",
                  "auth_required": true,
                  "registration_locked": false,
                  "oauth_google_enabled": false,
                  "oauth_apple_enabled": true,
                  "legal_document_version": "2026-07-13",
                  "minimum_supported_clients": {},
                  "recommended_clients": {},
                  "store_urls": {},
                  "maintenance_mode": false,
                  "future_server_field": "ignored"
                }
            """.trimIndent()))
            val client = ThoughtPinsApiClient(server.url("/").toString(), MemorySessionStore())

            val config = client.clientConfig()

            assertEquals("Thought Pins", config.appName)
            assertEquals(true, config.oauthAppleEnabled)
            assertEquals(false, config.oauthGoogleEnabled)
        }
    }

    @Test
    fun `authenticated request rotates an expired session once and retries with the new token`() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"expired\"}"))
            server.enqueue(MockResponse().setBody("""
                {
                  "access_token": "new-access",
                  "refresh_token": "new-refresh",
                  "token_type": "bearer",
                  "expires_in": 3600
                }
            """.trimIndent()))
            server.enqueue(MockResponse().setBody("""
                {
                  "id": "user-1",
                  "email": "review@example.com",
                  "auth_method": "password"
                }
            """.trimIndent()))
            val sessions = MemorySessionStore()
            sessions.save(ApiSession("old-access", "old-refresh"))
            val client = ThoughtPinsApiClient(server.url("/").toString(), sessions)

            val me = client.me()

            assertEquals("user-1", me.id)
            assertEquals(ApiSession("new-access", "new-refresh"), sessions.load())
            val first = server.takeRequest()
            val refresh = server.takeRequest()
            val retried = server.takeRequest()
            assertEquals("Bearer old-access", first.getHeader("Authorization"))
            assertEquals("/v1/auth/refresh", refresh.path)
            assertNull(refresh.getHeader("Authorization"))
            assertEquals("Bearer new-access", retried.getHeader("Authorization"))
        }
    }

    @Test
    fun `resumable vault import stages previews and applies before returning`() = runBlocking {
        MockWebServer().use { server ->
            val archive = "small vault".toByteArray()
            server.enqueue(MockResponse().setBody(vaultSession("uploading", 0)))
            server.enqueue(MockResponse().setBody(vaultSession("uploaded", archive.size)))
            server.enqueue(MockResponse().setBody(vaultSession("previewing", archive.size)))
            server.enqueue(MockResponse().setBody(vaultSession("preview_ready", archive.size)))
            server.enqueue(MockResponse().setBody(vaultSession("applying", archive.size)))
            server.enqueue(MockResponse().setBody(vaultSession("completed", archive.size, includeResult = true)))
            val sessions = MemorySessionStore()
            sessions.save(ApiSession("access", "refresh"))
            val client = ThoughtPinsApiClient(server.url("/").toString(), sessions)

            val result = client.importObsidianVaultResumable(
                filename = "Vault.zip",
                contentBase64 = java.util.Base64.getEncoder().encodeToString(archive),
            )

            assertEquals(1, result.imported)
            val requests = List(6) { server.takeRequest() }
            assertEquals("/v1/import/obsidian/uploads", requests[0].path)
            assertEquals("/v1/import/obsidian/uploads/transfer-1/chunks", requests[1].path)
            assertEquals("PUT", requests[1].method)
            assertNotNull(requests[1].getHeader("Idempotency-Key"))
            assertEquals("/v1/import/obsidian/uploads/transfer-1/preview", requests[2].path)
            assertEquals("/v1/import/obsidian/uploads/transfer-1", requests[3].path)
            assertEquals("/v1/import/obsidian/uploads/transfer-1/apply", requests[4].path)
            assertEquals("/v1/import/obsidian/uploads/transfer-1", requests[5].path)
        }
    }

    private fun vaultSession(status: String, receivedBytes: Int, includeResult: Boolean = false): String {
        val result = if (includeResult) vaultResult() else "null"
        return """{
            "id":"transfer-1","status":"$status","operation":null,"filename":"Vault.zip",
            "mode":"auto","conflict_policy":"skip","expected_bytes":11,"received_bytes":$receivedBytes,
            "archive_sha256":null,"progress_current":0,"progress_total":0,"progress_percent":0.0,
            "progress_stage":"$status","cancel_requested":false,"result":$result,"error":null
        }""".trimIndent()
    }

    private fun vaultResult(): String = """{
        "status":"completed","format":"obsidian_zip","mode":"auto","thoughtpins_export":false,
        "dry_run":false,"archive_sha256":"abc","files_discovered":1,"notes_discovered":1,
        "attachments_skipped":0,"structural_files_skipped":0,"canvases_discovered":0,
        "canvas_documents_imported":0,"journal_notes":1,"library_notes":0,"journal_jobs_queued":1,
        "library_documents_imported":0,"new_notes":1,"changed_notes":0,"unchanged_notes":0,
        "conflicts":0,"duplicates":0,"skipped":0,"imported":1,"warnings":[],"errors":[],
        "job_ids":["job-1"],"document_ids":[],"preview_items":[]
    }""".trimIndent()
}
