import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

public struct ThoughtPinsRootView: View {
    @StateObject private var model: ThoughtPinsAppModel
    @StateObject private var uploadProvider: ThoughtPinsDocumentPickerUploadProvider
    @StateObject private var voiceRecorder: ThoughtPinsVoiceRecorder

    public init(
        baseURL: URL,
        oauthTokenProvider: any ThoughtPinsOAuthTokenProvider = UnconfiguredThoughtPinsOAuthTokenProvider()
    ) {
        let uploadProvider = ThoughtPinsDocumentPickerUploadProvider()
        _uploadProvider = StateObject(wrappedValue: uploadProvider)
        _model = StateObject(
            wrappedValue: ThoughtPinsAppModel(
                baseURL: baseURL,
                oauthTokenProvider: oauthTokenProvider,
                uploadProvider: uploadProvider
            )
        )
        _voiceRecorder = StateObject(wrappedValue: ThoughtPinsVoiceRecorder())
    }

    public var body: some View {
        Group {
            if model.isAuthenticated {
                if !model.aiProcessingConsentAccepted {
                    ThoughtPinsAIConsentView(model: model)
                } else if model.isBlockedByInviteGate {
                    // After consent, so the account is fully created and its
                    // details kept before the wall appears — the same order the
                    // web app uses.
                    ThoughtPinsInviteView(model: model)
                } else {
                    ThoughtPinsMainShell(model: model, voiceRecorder: voiceRecorder)
                }
            } else {
                ThoughtPinsAuthView(model: model)
            }
        }
        .task { await model.bootstrap() }
        .fileImporter(
            isPresented: $uploadProvider.isImporterPresented,
            allowedContentTypes: [.item, .text, .pdf, .image, .audio],
            allowsMultipleSelection: false
        ) { result in
            Task { @MainActor in uploadProvider.completeFileImport(result) }
        }
        .overlay(alignment: .top) {
            if let message = model.maintenanceMessage ?? model.banner {
                Text(message)
                    .font(.footnote)
                    .padding(10)
                    .frame(maxWidth: .infinity)
                    .background(.thinMaterial)
                    .accessibilityIdentifier("thoughtpins-status-banner")
                    // This overlay sits on top of the navigation bar. Measured
                    // on an iPhone 13 Pro Max it spans y 0-82.7 while the
                    // Account button occupies y 52-86, so it covered about 90%
                    // of the only route to export, sign out, and account
                    // deletion -- which Guideline 5.1.1(v) requires to be
                    // reachable. Taps now pass through to what is underneath.
                    .allowsHitTesting(false)
                    // And it used to stay forever: nothing anywhere set
                    // `banner` back to nil, so "Signed in." was still sitting
                    // over the toolbar days later. Maintenance is excluded
                    // because that is a standing condition, not a status
                    // message.
                    .task(id: message) {
                        guard model.maintenanceMessage == nil else { return }
                        try? await Task.sleep(nanoseconds: 4_000_000_000)
                        if model.banner == message {
                            model.banner = nil
                        }
                    }
            }
        }
    }
}

struct ThoughtPinsAuthView: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var identifier = ""
    @State private var password = ""
    @State private var phone = ""
    @State private var legalAccepted = false
    @Environment(\.colorScheme) private var colorScheme

    /// Whether a provider can actually produce a button.
    ///
    /// These gate the section header as well as the rows inside it. The header
    /// used to be gated on the server flags alone while the Google row also
    /// required `supportsOAuth`, so a build without a Google client ID drew an
    /// "Other ways to sign in" header over an empty section. That is the
    /// current production shape: client-config reports google enabled and apple
    /// disabled, and GIDClientID is empty in any build that has not had the
    /// client IDs injected.
    private var appleSignInAvailable: Bool {
        model.config?.oauthAppleEnabled == true
    }

    /// Google is only offered when Sign in with Apple is offered alongside it.
    ///
    /// Guideline 4.8 requires that an app using a third-party login service
    /// also offer an equivalent option that limits collection to name and
    /// email **and lets the person keep their email address private**. Our
    /// email-and-password sign-up does not meet the second half of that: it
    /// needs a real, working address. Sign in with Apple is the option that
    /// does, so Google without Apple is a 4.8 rejection waiting to happen.
    ///
    /// Deciding it here rather than in server config means no flag flipped
    /// during the review window can put the binary out of compliance. To offer
    /// Google, configure Apple sign-in and turn `oauth_apple_enabled` on; the
    /// two then appear together. Email and password are unaffected either way.
    private var googleSignInAvailable: Bool {
        model.config?.oauthGoogleEnabled == true
            && model.supportsOAuth(.google)
            && appleSignInAvailable
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 10) {
                        ThoughtPinsBrandMark()
                            .frame(width: 72, height: 72)
                        Text("Thought Pins")
                            .font(.system(.title, design: .serif).weight(.medium))
                        Text("A private place to keep what matters.")
                            .font(.system(.subheadline, design: .serif)).italic()
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                Section("Account") {
                    TextField("Email", text: $identifier)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                    TextField("Phone", text: $phone)
                        .textContentType(.telephoneNumber)
                        .keyboardType(.phonePad)
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                }

                if appleSignInAvailable || googleSignInAvailable {
                    Section("Other ways to sign in") {
                        if appleSignInAvailable {
                            SignInWithAppleButton(.signIn) { request in
                                model.configureAppleSignInRequest(request)
                            } onCompletion: { result in
                                Task { await model.completeAppleSignIn(result) }
                            }
                            // Apple's guidance is a button that contrasts with
                            // the sheet behind it; a black button on the dark
                            // form background reads as a blank row.
                            .signInWithAppleButtonStyle(colorScheme == .dark ? .white : .black)
                            .frame(height: 44)
                        }
                        if googleSignInAvailable {
                            Button(ThoughtPinsOAuthProvider.google.label) {
                                Task { await model.oauthLogin(provider: .google) }
                            }
                        }
                    }
                }

                // The consent toggle used to live in this section's footer,
                // where SwiftUI renders it as secondary grey text. It gates
                // Create account, so the one control that unlocks registration
                // looked like a caption under a disabled button.
                Section("Before you create an account") {
                    Toggle("I consent to private AI processing of content I choose to send.", isOn: $legalAccepted)
                    HStack(spacing: 12) {
                        Link("Privacy", destination: model.legalURL(configured: model.config?.privacyPolicyUrl, fallbackPath: "/privacy"))
                        Link("Terms", destination: model.legalURL(configured: model.config?.termsUrl, fallbackPath: "/terms"))
                        Link("AI Disclosure", destination: model.legalURL(configured: model.config?.aiDisclosureUrl, fallbackPath: "/ai-disclosure"))
                    }
                    .font(.footnote)
                }

                Section {
                    Button("Sign in") {
                        Task { await model.login(identifier: identifier.isEmpty ? phone : identifier, password: password) }
                    }
                    .disabled(model.authBusy)
                    Button("Create account") {
                        Task {
                            await model.register(
                                email: identifier.isEmpty ? nil : identifier,
                                phone: phone.isEmpty ? nil : phone,
                                password: password,
                                consentToAIProcessing: legalAccepted
                            )
                        }
                    }
                    .disabled(model.authBusy || registrationBlocker != nil)
                    if model.authBusy {
                        HStack(spacing: 8) {
                            ProgressView()
                            Text("Signing in…")
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("Signing in")
                        .accessibilityIdentifier("thoughtpins-auth-progress")
                    }
                } footer: {
                    if let registrationBlocker {
                        Text(registrationBlocker)
                    }
                }
            }
            .navigationTitle("Thought Pins")
        }
    }

    /// Why Create account is disabled, or nil when it is not.
    ///
    /// A disabled button with no stated reason is the shape of a failed App
    /// Review: the reviewer cannot register, and nothing on screen says which
    /// of three rules they have not met yet.
    private var registrationBlocker: String? {
        if identifier.isEmpty && phone.isEmpty {
            return "Add an email address or phone number to create an account."
        }
        // Code points, matching the server's own length rule, so the client
        // never accepts a password the API is about to reject.
        let length = password.unicodeScalars.count
        if length < 12 {
            return "Choose a password of at least 12 characters."
        }
        if length > 256 {
            return "Choose a password of 256 characters or fewer."
        }
        if !legalAccepted {
            return "Accept AI processing above to create an account."
        }
        return nil
    }
}

struct ThoughtPinsAIConsentView: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var confirmed = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 12) {
                        ThoughtPinsBrandMark()
                            .frame(width: 72, height: 72)
                        Text("Your memories stay under your control")
                            .font(.system(.title2, design: .serif).weight(.semibold))
                            .multilineTextAlignment(.center)
                        Text("Thought Pins sends the content you choose to save or discuss to configured AI services so it can organize memories and answer with context. It does not use that content for advertising.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }
                Section("Review") {
                    Link("Privacy Policy", destination: model.legalURL(configured: model.config?.privacyPolicyUrl, fallbackPath: "/privacy"))
                    Link("AI Disclosure", destination: model.legalURL(configured: model.config?.aiDisclosureUrl, fallbackPath: "/ai-disclosure"))
                    Toggle("I understand and allow this processing.", isOn: $confirmed)
                    Button("Continue") {
                        Task { await model.acceptLegal(document: "ai_disclosure") }
                    }
                    .disabled(!confirmed)
                }
            }
            .navigationTitle("Before you continue")
        }
    }
}

@MainActor
public final class ThoughtPinsVoiceRecorder: ObservableObject {
    @Published public private(set) var isRecording = false
    @Published public private(set) var errorMessage: String?
    private var recorder: AVAudioRecorder?
    private var recordingURL: URL?

    public init() {}

    public func start() async {
        guard !isRecording else { return }
        errorMessage = nil
        let granted = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { allowed in
                continuation.resume(returning: allowed)
            }
        }
        guard granted else {
            errorMessage = "Microphone access was not granted. You can attach an audio file instead."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .spokenAudio, options: [.allowBluetooth])
            try session.setActive(true)
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("thoughtpins-voice-\(UUID().uuidString).m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            // record() reports whether the hardware actually started. Ignoring
            // it showed a live recording indicator over a microphone that never
            // opened, and stop() then uploaded an empty file.
            guard recorder.record() else {
                try? FileManager.default.removeItem(at: url)
                try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
                errorMessage = "The microphone could not start. You can attach an audio file instead."
                return
            }
            self.recorder = recorder
            recordingURL = url
            isRecording = true
        } catch {
            errorMessage = "The microphone could not start. You can attach an audio file instead."
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
    }

    public func stop() -> Data? {
        guard isRecording else { return nil }
        recorder?.stop()
        recorder = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        guard let recordingURL else { return nil }
        defer {
            try? FileManager.default.removeItem(at: recordingURL)
            self.recordingURL = nil
        }
        return try? Data(contentsOf: recordingURL)
    }

    public func cancel() {
        recorder?.stop()
        recorder = nil
        isRecording = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        if let recordingURL {
            try? FileManager.default.removeItem(at: recordingURL)
            self.recordingURL = nil
        }
    }
}


/// The closed-beta wall.
///
/// Registration is deliberately open, so an account can exist before it may be
/// used. Without this the shell rendered a signed-in app whose every request
/// came back 403 — indistinguishable from a broken build, and exactly what a
/// store reviewer would report. The server enforces the gate on its own; this
/// exists so the person is told what is happening.
struct ThoughtPinsInviteView: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var code = ""
    @State private var showingDeleteConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 12) {
                        ThoughtPinsBrandMark()
                            .frame(width: 72, height: 72)
                        Text("You're on the list")
                            .font(.system(.title2, design: .serif).weight(.semibold))
                        Text("Thought Pins is in private testing. Your account is saved — enter an invite code to start using it.")
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                }

                Section("Invite code") {
                    TextField("Invite code", text: $code)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .disabled(model.inviteBusy)
                    Button(model.inviteBusy ? "Checking…" : "Redeem code") {
                        Task { await model.redeemInvite(code) }
                    }
                    .disabled(code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.inviteBusy)

                    if let remaining = model.inviteStatus?.attemptsRemaining, (1...3).contains(remaining) {
                        Text("\(remaining) attempts remaining.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if let email = model.inviteStatus?.contactEmail, !email.isEmpty {
                    Section {
                        Text("No code yet? Email \(email) and we will add you.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                // Both deliberately reachable from behind the gate. An account
                // that cannot use the product must still be able to leave it,
                // and Guideline 5.1.1(v) wants deletion findable in the app —
                // which has to include the screen a blocked account is looking at.
                Section("Account") {
                    Button("Sign out") { Task { await model.logout() } }
                    Button("Delete account", role: .destructive) { showingDeleteConfirmation = true }
                }
            }
            .navigationTitle("Private testing")
            .confirmationDialog(
                "Permanently delete your Thought Pins account?",
                isPresented: $showingDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete account", role: .destructive) { Task { await model.deleteAccount() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Your account and anything saved with it are removed. This cannot be undone.")
            }
        }
    }
}
