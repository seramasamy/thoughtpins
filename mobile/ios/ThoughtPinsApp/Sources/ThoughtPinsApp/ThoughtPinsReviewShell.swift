import Foundation
import AuthenticationServices
import AVFoundation
import PhotosUI
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

public struct ThoughtPinsRootView: View {
    @StateObject private var model: ThoughtPinsAppModel
    @StateObject private var uploadProvider: ThoughtPinsDocumentPickerUploadProvider
    @StateObject private var voiceRecorder: ThoughtPinsVoiceRecorder
    /// Held here rather than in the provider because PhotosPicker binds to
    /// a `PhotosPickerItem`, which is a SwiftUI/PhotosUI type; keeping it out
    /// of the provider leaves that type out of the upload protocol.
    @State private var pickedPhoto: PhotosPickerItem?

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
            // Checked before anything else, including sign-in: a build the
            // server has withdrawn should not be able to create accounts or
            // write entries either.
            if model.versionDecision?.status == .blocked {
                ThoughtPinsUpdateRequiredView(model: model)
            } else if model.isAuthenticated {
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
        // A standing condition, so it inserts rather than overlays: it pushes the
        // content down instead of sitting on the navigation bar the way the
        // transient banner does. The wording deliberately does not claim we are
        // showing anything fresh -- offline the read screens are empty because
        // we could not load them, not because there is nothing there.
        .safeAreaInset(edge: .top) {
            if model.isOffline, model.isAuthenticated {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.slash")
                    Text("Offline. Anything you write is saved on this device and sent when you reconnect.")
                }
                .font(.footnote)
                .foregroundStyle(ThoughtPinsTheme.inkSoft)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity)
                .background(ThoughtPinsTheme.brandSoft)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("thoughtpins-offline-notice")
            }
        }
        .tint(ThoughtPinsTheme.action)
        .task { await model.bootstrap() }
        // The onCancellation handler is load-bearing: the base fileImporter
        // overload never calls onCompletion when the person cancels (or swipes
        // the sheet away), which stranded the awaiting continuation and wedged
        // file import until relaunch -- the import button's task hung forever
        // and every later attempt failed as "already in progress".
        .fileImporter(
            isPresented: $uploadProvider.isImporterPresented,
            allowedContentTypes: [.item, .text, .pdf, .image, .audio],
            allowsMultipleSelection: false,
            onCompletion: { result in
                Task { @MainActor in uploadProvider.completeFileImport(result) }
            },
            onCancellation: {
                Task { @MainActor in uploadProvider.cancelFileImport() }
            }
        )
        // Files cannot browse the photo library, so `.image` above only ever
        // reached image *files*. A photo from the camera roll — the obvious
        // thing to attach to a journal entry — needs PhotosPicker, which runs
        // out of process and therefore requires no photo-library permission and
        // no usage-description key.
        .confirmationDialog(
            "Add from",
            isPresented: $uploadProvider.isSourceChoicePresented,
            titleVisibility: .visible
        ) {
            Button("Photo Library") { uploadProvider.choosePhotos() }
            Button("Files") { uploadProvider.chooseFiles() }
            Button("Cancel", role: .cancel) { uploadProvider.cancelSourceChoice() }
        }
        .photosPicker(
            isPresented: $uploadProvider.isPhotoPickerPresented,
            selection: $pickedPhoto,
            matching: .images
        )
        // Zero-argument closure, reading the value from state.
        //
        // `onChange(of:initial:_:)` has both a `(V, V) -> Void` and a
        // `() -> Void` form. For `PhotosPickerItem?` the compiler settles on the
        // second: a two-argument closure was rejected with "expects 1 argument,
        // but 2 were used", and a one-argument closure with "expects 0
        // arguments, but 1 was used". `scenePhase` in ThoughtPinsScreens.swift
        // takes the two-argument form, so this is a property of the type, not of
        // the deployment target. Reading `pickedPhoto` directly sidesteps the
        // question entirely and cannot be resolved to the wrong overload.
        .onChange(of: pickedPhoto) {
            // Only a real selection. Clearing the binding below sets this to nil
            // again, and that is not an event worth reacting to.
            guard let item = pickedPhoto else { return }
            uploadProvider.beginPhotoSelection()
            Task { @MainActor in
                let data = try? await item.loadTransferable(type: Data.self)
                // PhotosPicker supplies no filename. Milliseconds since the
                // epoch: sortable, collision-free in practice, and it needs no
                // formatter — an earlier attempt added a `private extension
                // ISO8601DateFormatter` for this and cost a build when the
                // extension did not land.
                let stamp = Int(Date().timeIntervalSince1970 * 1000)
                uploadProvider.completePhotoImport(
                    data: data,
                    filename: "photo-\(stamp).jpg",
                    mediaType: "image/jpeg"
                )
                pickedPhoto = nil
            }
        }
        // The only cancellation signal PhotosPicker gives: dismissal flips the
        // binding. `photoPickerDismissed` ignores it when a selection is in
        // flight, so this cancels an abandoned pick without cancelling a good
        // one.
        .onChange(of: uploadProvider.isPhotoPickerPresented) {
            guard !uploadProvider.isPhotoPickerPresented else { return }
            uploadProvider.photoPickerDismissed()
        }
        // Problems inset rather than overlay, so one that stays does not sit on
        // the navigation bar, and so it can carry its own dismiss control.
        .safeAreaInset(edge: .top) {
            if model.maintenanceMessage == nil, model.bannerIsProblem, let message = model.banner {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: "exclamationmark.circle")
                    Text(message)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        // The identifier belongs on the text, not the stack: a
                        // plain HStack is not an accessibility element, so an
                        // identifier there never reaches the tree at all. It
                        // also must not be combined with the button, or the
                        // button stops being separately reachable.
                        .accessibilityIdentifier("thoughtpins-problem-banner")
                    Button("Dismiss") { model.dismissBanner() }
                        .font(.footnote.weight(.semibold))
                        .accessibilityIdentifier("thoughtpins-problem-dismiss")
                }
                .font(.footnote)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity)
                .background(ThoughtPinsTheme.brandSoft)
            }
        }
        .overlay(alignment: .top) {
            if let message = model.maintenanceMessage ?? (model.bannerIsProblem ? nil : model.banner) {
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
                    // Only successes time out. A problem is something the
                    // person may need to act on, and four seconds was hiding
                    // failures before they could be read.
                    .task(id: message) {
                        guard model.maintenanceMessage == nil, !model.bannerIsProblem else { return }
                        try? await Task.sleep(nanoseconds: 4_000_000_000)
                        if model.banner == message, !model.bannerIsProblem {
                            model.dismissBanner()
                        }
                    }
            }
        }
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
                            .font(.system(.title2, design: .default).weight(.semibold))
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

    /// Fires when iOS takes the audio session away mid-recording.
    ///
    /// A phone call interrupts the session and stops the hardware, but does not
    /// necessarily background the app -- the compact call banner leaves the
    /// scene active -- so the scenePhase teardown never runs. isRecording stayed
    /// true, the button still read Stop, and the pulsing indicator sat over a
    /// microphone iOS had already closed.
    public var onInterruption: (() -> Void)?

    public init() {
        NotificationCenter.default.addObserver(
            forName: AVAudioSession.interruptionNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] notification in
            guard
                let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                AVAudioSession.InterruptionType(rawValue: raw) == .began
            else {
                return
            }
            MainActor.assumeIsolated {
                guard let self, self.isRecording else { return }
                self.onInterruption?()
            }
        }
    }

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
        // Which call failed, for the message below. A single "could not start"
        // for four different failures is undiagnosable from a device, which is
        // exactly where this first went wrong.
        var stage = "session"
        do {
            let session = AVAudioSession.sharedInstance()
            // `.spokenAudio` is a *playback* mode — Apple documents it for
            // continuous spoken content like audiobooks, so it can pause under
            // interruption. Pairing it with the `.record` category asks the
            // session for a combination that has no meaning, and the throw
            // surfaced as "the microphone could not start" on an iPhone 17 Pro
            // Max running iOS 26. `.default` is the mode for plain recording.
            try session.setCategory(.record, mode: .default, options: [.allowBluetooth])
            try session.setActive(true)
            stage = "recorder"
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("thoughtpins-voice-\(UUID().uuidString).m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            // Allocate the hardware and create the file before asking it to
            // run. `record()` prepares implicitly when it has to, but doing it
            // explicitly separates "could not get the microphone" from "asked
            // it to start and it refused", and it is what Apple's own sample
            // code does.
            stage = "prepare"
            guard recorder.prepareToRecord() else {
                try? FileManager.default.removeItem(at: url)
                try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
                errorMessage = "The microphone could not start (prepare). You can attach an audio file instead."
                return
            }
            // record() reports whether the hardware actually started. Ignoring
            // it showed a live recording indicator over a microphone that never
            // opened, and stop() then uploaded an empty file.
            stage = "record"
            guard recorder.record() else {
                try? FileManager.default.removeItem(at: url)
                try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
                errorMessage = "The microphone could not start (record). You can attach an audio file instead."
                return
            }
            self.recorder = recorder
            recordingURL = url
            isRecording = true
        } catch {
            // Naming the stage costs the person nothing and is the difference
            // between "it broke" and a fix. Without it, four distinct failures
            // produced one sentence, and the only way to tell them apart was to
            // guess and spend a build.
            errorMessage = "The microphone could not start (\(stage)). You can attach an audio file instead."
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


/// The invitation wall shown to an account that is not yet admitted.
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
                        Text("Invitation required")
                            .font(.system(.title2, design: .default).weight(.semibold))
                        Text("Thought Pins is invitation-only right now. Your account is saved — enter an invite code to start using it.")
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
            .navigationTitle("Invitation required")
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
