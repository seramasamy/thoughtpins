package com.thoughtpins.app

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.core.content.edit
import com.thoughtpins.core.ApiSession
import com.thoughtpins.core.DraftStorage
import com.thoughtpins.core.SessionStore
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private const val KEYSTORE_PROVIDER = "AndroidKeyStore"
private const val KEY_ALIAS = "thoughtpins_native_shell_v1"
private const val CIPHER_TRANSFORMATION = "AES/GCM/NoPadding"
private const val GCM_TAG_BITS = 128

class AndroidSecureSessionStore(
    context: Context,
    private val json: Json = Json { ignoreUnknownKeys = true },
) : SessionStore {
    private val strings = EncryptedPreferences(context.applicationContext, "thoughtpins_secure_session")

    override suspend fun load(): ApiSession? =
        strings.read("api_session")?.let { json.decodeFromString<ApiSession>(it) }

    override suspend fun save(session: ApiSession?) {
        if (session == null) {
            strings.remove("api_session")
        } else {
            strings.write("api_session", json.encodeToString(session))
        }
    }
}

class AndroidEncryptedDraftStorage(context: Context) : DraftStorage {
    private val strings = EncryptedPreferences(context.applicationContext, "thoughtpins_secure_drafts")

    override suspend fun read(): String? = strings.read("capture_drafts")

    override suspend fun write(value: String) {
        strings.write("capture_drafts", value)
    }
}

private class EncryptedPreferences(context: Context, name: String) {
    private val prefs: SharedPreferences = context.getSharedPreferences(name, Context.MODE_PRIVATE)
    private val keyStore: KeyStore = KeyStore.getInstance(KEYSTORE_PROVIDER).apply { load(null) }

    fun read(key: String): String? {
        val encoded = prefs.getString(key, null) ?: return null
        return runCatching { decrypt(encoded) }
            .onFailure { remove(key) }
            .getOrNull()
    }

    fun write(key: String, value: String) {
        prefs.edit { putString(key, encrypt(value)) }
    }

    fun remove(key: String) {
        prefs.edit { remove(key) }
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val ciphertext = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val iv = Base64.encodeToString(cipher.iv, Base64.NO_WRAP)
        val body = Base64.encodeToString(ciphertext, Base64.NO_WRAP)
        return "$iv:$body"
    }

    private fun decrypt(encoded: String): String {
        val parts = encoded.split(":", limit = 2)
        require(parts.size == 2) { "Malformed encrypted value." }
        val iv = Base64.decode(parts[0], Base64.NO_WRAP)
        val ciphertext = Base64.decode(parts[1], Base64.NO_WRAP)
        val cipher = Cipher.getInstance(CIPHER_TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    private fun getOrCreateKey(): SecretKey {
        val existing = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry
        if (existing != null) return existing.secretKey

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE_PROVIDER)
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build()
        generator.init(spec)
        return generator.generateKey()
    }
}
