package com.thoughtpins.app

import android.app.Activity
import android.util.Base64
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.credentials.exceptions.NoCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.thoughtpins.app.ui.NativeOAuthCredential
import com.thoughtpins.app.ui.NativeOAuthTokenProvider
import com.thoughtpins.app.ui.ThoughtPinsOAuthProvider
import java.security.SecureRandom

class AndroidGoogleOAuthTokenProvider(
    private val activity: Activity,
    private val serverClientId: String,
) : NativeOAuthTokenProvider {
    private val credentialManager = CredentialManager.create(activity)

    override fun supports(provider: ThoughtPinsOAuthProvider): Boolean =
        provider == ThoughtPinsOAuthProvider.GOOGLE && serverClientId.isNotBlank()

    override suspend fun credential(provider: ThoughtPinsOAuthProvider): NativeOAuthCredential {
        require(supports(provider)) { "Google sign-in is not configured in this build." }
        val nonce = secureNonce()
        val option = GetSignInWithGoogleOption.Builder(serverClientId)
            .setNonce(nonce)
            .build()
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(option)
            .build()
        val result = try {
            credentialManager.getCredential(
                context = activity,
                request = request,
            )
        } catch (error: NoCredentialException) {
            throw IllegalStateException("No Google account is available. Add an account or use email sign-in.", error)
        } catch (error: GetCredentialCancellationException) {
            throw IllegalStateException("Google sign-in was canceled.", error)
        } catch (error: GetCredentialException) {
            throw IllegalStateException("Google sign-in could not be completed.", error)
        }
        val custom = result.credential as? CustomCredential
            ?: error("Google did not return a supported sign-in credential.")
        require(custom.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            "Google returned an unexpected credential type."
        }
        val google = GoogleIdTokenCredential.createFrom(custom.data)
        return NativeOAuthCredential(
            idToken = google.idToken,
            displayName = google.displayName,
            nonce = nonce,
        )
    }

    private fun secureNonce(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return Base64.encodeToString(bytes, Base64.NO_WRAP or Base64.URL_SAFE or Base64.NO_PADDING)
    }
}
