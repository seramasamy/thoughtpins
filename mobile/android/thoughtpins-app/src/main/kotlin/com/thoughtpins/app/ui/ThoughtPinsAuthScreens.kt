package com.thoughtpins.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp


@Composable
internal fun ThoughtPinsAuthScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    var email by rememberSaveable { mutableStateOf("") }
    var phone by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var legalAccepted by rememberSaveable { mutableStateOf(false) }
    // Why Create account is disabled, or null when it is not. Code points, so
    // the client never accepts a password the API is about to reject on length.
    val registrationBlocker: String? = when {
        email.isBlank() && phone.isBlank() -> "Add an email address or phone number to create an account."
        password.codePointCount(0, password.length) < 12 -> "Choose a password of at least 12 characters."
        password.codePointCount(0, password.length) > 256 -> "Choose a password of 256 characters or fewer."
        !legalAccepted -> "Accept AI processing above to create an account."
        else -> null
    }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(top = 24.dp, bottom = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ThoughtPinsBrandMark(Modifier.size(72.dp))
            Text("Thought Pins", style = MaterialTheme.typography.headlineMedium)
            Text(
                "A private place to keep what matters.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        state.maintenanceMessage?.let { MaintenanceBanner(it) }
        state.banner?.let {
            Text(
                it,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
        OutlinedTextField(
            email,
            { email = it },
            label = { Text("Email") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            phone,
            { phone = it },
            label = { Text("Phone") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            password,
            { password = it },
            label = { Text("Password") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            modifier = Modifier.fillMaxWidth(),
        )
        // Consent sits above the buttons it controls. It used to sit below
        // them, so "Create account" rendered greyed out with the one control
        // that enables it further down the screen — visible in the first
        // emulator run, and the shape of a store rejection that says the
        // reviewer could not create an account.
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = legalAccepted,
                onCheckedChange = { legalAccepted = it },
                modifier = Modifier.sizeIn(minWidth = 48.dp, minHeight = 48.dp),
            )
            Text(
                "I consent to private AI processing of content I choose to send.",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Button(
                onClick = { viewModel.login(if (email.isBlank()) phone else email, password) },
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text("Sign in") }
            TextButton(
                onClick = { viewModel.register(email.ifBlank { null }, phone.ifBlank { null }, password, legalAccepted) },
                enabled = registrationBlocker == null,
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text("Create account") }
        }
        // A disabled button with no stated reason is why reviewers file
        // "unable to create an account".
        registrationBlocker?.let { reason ->
            Text(reason, style = MaterialTheme.typography.bodySmall)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TextButton(
                onClick = {
                    viewModel.openLegalLink("Privacy Policy", legalUrl(state.clientConfig?.privacyPolicyUrl, "/privacy"))
                },
            ) { Text("Privacy") }
            TextButton(
                onClick = { viewModel.openLegalLink("Terms", legalUrl(state.clientConfig?.termsUrl, "/terms")) },
            ) { Text("Terms") }
            TextButton(
                onClick = {
                    viewModel.openLegalLink(
                        "AI Disclosure",
                        legalUrl(state.clientConfig?.aiDisclosureUrl, "/ai-disclosure"),
                    )
                },
            ) { Text("AI Disclosure") }
        }
        if (
            state.clientConfig?.oauthGoogleEnabled == true &&
            viewModel.supportsOAuth(ThoughtPinsOAuthProvider.GOOGLE)
        ) {
            TextButton(
                onClick = { viewModel.oauthLogin(ThoughtPinsOAuthProvider.GOOGLE) },
                modifier = Modifier.heightIn(min = 48.dp),
            ) {
                Text(ThoughtPinsOAuthProvider.GOOGLE.label)
            }
        }
    }
}


@Composable
internal fun ThoughtPinsAIConsentScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    var confirmed by rememberSaveable { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ThoughtPinsBrandMark(Modifier.size(72.dp))
        Text(
            "Your memories stay under your control",
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Text(
            "Thought Pins sends the content you choose to save or discuss to configured AI services so it can " +
                "organize memories and answer with context. It does not use that content for advertising.",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = confirmed, onCheckedChange = { confirmed = it })
            Text("I understand and allow this processing.")
        }
        Button(onClick = { viewModel.acceptLegal("ai_disclosure") }, enabled = confirmed) { Text("Continue") }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TextButton(
                onClick = {
                    viewModel.openLegalLink("Privacy Policy", legalUrl(state.clientConfig?.privacyPolicyUrl, "/privacy"))
                },
            ) { Text("Privacy") }
            TextButton(
                onClick = {
                    viewModel.openLegalLink(
                        "AI Disclosure",
                        legalUrl(state.clientConfig?.aiDisclosureUrl, "/ai-disclosure"),
                    )
                },
            ) { Text("AI Disclosure") }
        }
        state.banner?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
    }
}
