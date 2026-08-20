package com.thoughtpins.app

import android.Manifest
import android.content.ContentResolver
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.thoughtpins.app.ui.NativeExternalLinkOpener
import com.thoughtpins.app.ui.NativeUploadDestination
import com.thoughtpins.app.ui.NativeUploadPayload
import com.thoughtpins.app.ui.NativeUploadProvider
import com.thoughtpins.app.ui.NativeVoiceRecorder
import com.thoughtpins.app.ui.ThoughtPinsApp
import com.thoughtpins.core.DraftQueue
import com.thoughtpins.core.ThoughtPinsApiClient
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.OkHttpClient

class ThoughtPinsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        var pickerProvider: AndroidFileUploadProvider? = null
        val launcher = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            pickerProvider?.handlePickedUri(uri)
        }
        val uploadProvider = AndroidFileUploadProvider(contentResolver, launcher)
        pickerProvider = uploadProvider
        val voiceRecorder = AndroidVoiceRecorder(this)
        val api = ThoughtPinsApiClient(
            baseUrl = BuildConfig.THOUGHTPINS_API_BASE_URL,
            sessionStore = AndroidSecureSessionStore(applicationContext),
            http = OkHttpClient(),
        )
        val drafts = DraftQueue(AndroidEncryptedDraftStorage(applicationContext))
        val oauthProvider = AndroidGoogleOAuthTokenProvider(
            activity = this,
            serverClientId = BuildConfig.GOOGLE_SERVER_CLIENT_ID,
        )
        setContent {
            ThoughtPinsApp(
                api = api,
                draftQueue = drafts,
                oauthTokenProvider = oauthProvider,
                uploadProvider = uploadProvider,
                voiceRecorder = voiceRecorder,
                externalLinkOpener = AndroidExternalLinkOpener(this),
            )
        }
    }
}

@Suppress("DEPRECATION")
private class AndroidVoiceRecorder(
    private val activity: ComponentActivity,
) : NativeVoiceRecorder {
    private val _isRecording = MutableStateFlow(false)
    private val _errorMessage = MutableStateFlow<String?>(null)
    private var recorder: MediaRecorder? = null
    private var outputFile: java.io.File? = null

    private val permissionLauncher = activity.registerForActivityResult(ActivityResultContracts.RequestPermission()) { allowed ->
        if (allowed) beginRecording() else _errorMessage.value = "Microphone access was not granted. You can attach an audio file instead."
    }

    override val isRecording: StateFlow<Boolean> = _isRecording
    override val errorMessage: StateFlow<String?> = _errorMessage

    override fun start() {
        if (_isRecording.value) return
        _errorMessage.value = null
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            beginRecording()
        } else {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun beginRecording() {
        val file = java.io.File(activity.cacheDir, "thoughtpins-voice-${System.currentTimeMillis()}.m4a")
        try {
            val next = MediaRecorder()
            next.setAudioSource(MediaRecorder.AudioSource.MIC)
            next.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            next.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            next.setAudioSamplingRate(44_100)
            next.setAudioEncodingBitRate(128_000)
            next.setOutputFile(file.absolutePath)
            next.prepare()
            next.start()
            recorder = next
            outputFile = file
            _isRecording.value = true
        } catch (_: Exception) {
            recorder?.release()
            recorder = null
            file.delete()
            _errorMessage.value = "The microphone could not start. You can attach an audio file instead."
        }
    }

    override fun stop(): ByteArray? {
        val current = recorder ?: return null
        val file = outputFile
        return try {
            current.stop()
            current.release()
            recorder = null
            outputFile = null
            _isRecording.value = false
            file?.takeIf { it.isFile }?.readBytes()
        } catch (_: Exception) {
            current.release()
            recorder = null
            outputFile = null
            _isRecording.value = false
            _errorMessage.value = "The voice note could not be saved."
            null
        } finally {
            file?.delete()
        }
    }

    override fun cancel() {
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        _isRecording.value = false
        outputFile?.delete()
        outputFile = null
    }
}

private class AndroidFileUploadProvider(
    private val contentResolver: ContentResolver,
    private val launcher: ActivityResultLauncher<Array<String>>,
) : NativeUploadProvider {
    private var pending: CancellableContinuation<Uri?>? = null

    override suspend fun payload(destination: NativeUploadDestination): NativeUploadPayload {
        val uri: Uri = suspendCancellableCoroutine { continuation: CancellableContinuation<Uri?> ->
            if (pending != null) {
                continuation.resumeWithException(IllegalStateException("A file picker is already open."))
                return@suspendCancellableCoroutine
            }
            pending = continuation
            continuation.invokeOnCancellation { pending = null }
            launcher.launch(
                if (destination == NativeUploadDestination.OBSIDIAN_VAULT) {
                    arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream")
                } else {
                    arrayOf("text/*", "application/pdf", "image/*", "audio/*")
                }
            )
        } ?: error("No file selected.")
        val filename = displayName(uri) ?: uri.lastPathSegment?.substringAfterLast('/') ?: "thoughtpins-upload"
        val mediaType = contentResolver.getType(uri)
        val bytes = contentResolver.openInputStream(uri)?.use { input ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(16 * 1024)
            var total = 0
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                total += read
                if (total > 25 * 1024 * 1024) error("$filename exceeds the 25 MB upload limit.")
                output.write(buffer, 0, read)
            }
            output.toByteArray()
        } ?: error("Could not read selected file.")
        val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
        return NativeUploadPayload(
            filename = filename,
            contentBase64 = encoded,
            mediaType = mediaType,
            title = filename.substringBeforeLast('.', filename),
            sourceType = when (destination) {
                NativeUploadDestination.JOURNAL -> "journal_upload"
                else -> "file_upload"
            },
        )
    }

    fun handlePickedUri(uri: Uri?) {
        val continuation = pending ?: return
        pending = null
        continuation.resume(uri)
    }

    private fun displayName(uri: Uri): String? {
        return contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) return@use null
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0) cursor.getString(index) else null
        }
    }
}

private class AndroidExternalLinkOpener(
    private val activity: ComponentActivity,
) : NativeExternalLinkOpener {
    override suspend fun open(url: String) {
        val intent = Intent(Intent.ACTION_VIEW, url.toUri())
        activity.startActivity(intent)
    }
}
