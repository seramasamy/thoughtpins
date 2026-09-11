import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

struct ThoughtPinsChatScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @ObservedObject var voiceRecorder: ThoughtPinsVoiceRecorder
    @State private var text = ""
    @State private var lastQuestion = ""
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showingVoiceDisclosure = false
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("thoughtpins.voiceDisclosure.2026-07-13") private var voiceDisclosureAccepted = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @FocusState private var composerFocused: Bool
    @State private var showingReportDialog = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                if !dynamicTypeSize.isAccessibilitySize { privacyControls }
                ScrollViewReader { reader in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            if dynamicTypeSize.isAccessibilitySize {
                                privacyControls
                                privacyCaption
                            }
                            if !model.chatReply.isEmpty, let route = thoughtPinsRouteLabel(model.routeLabel) {
                                Text(route.uppercased())
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(ThoughtPinsTheme.inkSoft)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(ThoughtPinsTheme.brandSoft, in: Capsule())
                            }
                            if !lastQuestion.isEmpty {
                                HStack {
                                    Spacer(minLength: 28)
                                    Text(lastQuestion).font(.body).padding(16)
                                        .background(ThoughtPinsTheme.accentSoft, in: RoundedRectangle(cornerRadius: 20))
                                        .foregroundStyle(ThoughtPinsTheme.ink)
                                }
                            }
                            if model.chatReply.isEmpty && !model.isThinking {
                                ThoughtPinsChatWelcome { prompt in
                                    text = prompt
                                    submit()
                                }
                            } else if !model.isThinking {
                                ThoughtPinsReplyView(reply: model.chatReply)
                                    .id("thoughtpins-answer")
                                    .textSelection(.enabled)
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 11)
                                    .background(ThoughtPinsTheme.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                                            .stroke(ThoughtPinsTheme.line, lineWidth: 1)
                                    )
                                    .transition(.opacity.combined(with: .move(edge: .bottom)))
                            }
                            if !model.chatReply.isEmpty && !model.isThinking {
                                Button {
                                    showingReportDialog = true
                                } label: {
                                    Label("Report this reply", systemImage: "flag")
                                        .font(.caption)
                                }
                                .buttonStyle(.plain)
                                .foregroundStyle(ThoughtPinsTheme.inkSoft)
                                .padding(.horizontal, 4)
                                .frame(minHeight: 44)
                                .accessibilityIdentifier("thoughtpins-report-reply")
                                .accessibilityHint("Reports this answer to Thought Pins for review.")
                            }
                            if model.isThinking {
                                HStack(spacing: 8) {
                                    ThoughtPinsThinkingDots()
                                    Text("Thinking with your memory").font(.callout).foregroundStyle(.secondary)
                                }
                                .padding(.horizontal, 4)
                                .transition(.opacity)
                                .accessibilityElement(children: .combine)
                                .accessibilityLabel("Thought Pins is thinking with your memory")
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: model.chatReply)
                        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: model.isThinking)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: model.chatReply) { _, reply in
                        guard !reply.isEmpty else { return }
                        if reduceMotion {
                            reader.scrollTo("thoughtpins-answer", anchor: .top)
                        } else {
                            withAnimation(.easeInOut(duration: 0.22)) {
                                reader.scrollTo("thoughtpins-answer", anchor: .top)
                            }
                        }
                    }
                }
                ThoughtPinsChatComposer(text: $text, focused: $composerFocused,
                                        busy: model.isThinking, recording: voiceRecorder.isRecording,
                                        record: toggleRecording, submit: submit)
                if !dynamicTypeSize.isAccessibilitySize { privacyCaption }
                if voiceRecorder.isRecording {
                    Label("Recording voice note", systemImage: "waveform")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let error = voiceRecorder.errorMessage {
                    Text(error).font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding()
            .thoughtPinsReadableColumn(maxWidth: 800)
            .thoughtPinsScreen()
            .navigationTitle("Chat")
            .confirmationDialog(
                "Report this reply?",
                isPresented: $showingReportDialog,
                titleVisibility: .visible
            ) {
                Button("Unsafe or harmful") {
                    Task { await model.reportChatReply(category: "unsafe_ai_output") }
                }
                Button("Shows private information") {
                    Task { await model.reportChatReply(category: "privacy_concern") }
                }
                Button("Something else") {
                    Task { await model.reportChatReply(category: "other") }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The reply is sent to Thought Pins so a person can review it.")
            }
            .toolbar { ThoughtPinsAccountToolbar(model: model) }
            .alert("Record a voice note", isPresented: $showingVoiceDisclosure) {
                Button("Cancel", role: .cancel) {}
                Button("Continue") {
                    voiceDisclosureAccepted = true
                    Task { await voiceRecorder.start() }
                }
            } message: {
                Text(model.config?.voiceArchiveEnabled == true
                    ? "Thought Pins sends this recording for transcription. Audio is discarded after processing unless you separately enable Personal voice archive in Account."
                    : "Thought Pins sends this recording for transcription and discards the audio after processing. The transcript is saved as a journal entry.")
            }
            .task(id: voiceRecorder.isRecording) {
                guard voiceRecorder.isRecording else { return }
                try? await Task.sleep(nanoseconds: 600_000_000_000)
                guard !Task.isCancelled, voiceRecorder.isRecording else { return }
                finishVoiceRecording()
            }
            // Backgrounding does not fire onDisappear, and the app has no audio
            // background mode, so iOS tears the session down while the button
            // still reads Stop and isRecording stays true forever. Close the
            // recording out here and keep what was captured.
            .onChange(of: scenePhase) { _, phase in
                if phase != .active, voiceRecorder.isRecording {
                    finishVoiceRecording()
                }
            }
            // A phone call stops the hardware without backgrounding the app, so
            // the scenePhase branch above never sees it. Close the recording out
            // the same way and keep what was captured.
            .onAppear {
                voiceRecorder.onInterruption = { finishVoiceRecording() }
            }
            .onDisappear {
                if voiceRecorder.isRecording {
                    voiceRecorder.cancel()
                }
            }
        }
    }

    private var privacyControls: some View {
        HStack(spacing: 10) {
            if !dynamicTypeSize.isAccessibilitySize {
                Label("Your memory", systemImage: "sparkle")
                    .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                Spacer(minLength: 8)
            }
            Toggle(isOn: Binding(get: { model.usePrivateMemories }, set: { model.setUsePrivateMemories($0) })) {
                Label("Private", systemImage: "lock").font(.caption.weight(.medium))
            }
            .frame(maxWidth: dynamicTypeSize.isAccessibilitySize ? .infinity : 166)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityLabel("Use private memories")
            .accessibilityHint("When off, private memories stay out of this reply.")
        }
        .padding(.vertical, 6)
    }

    private var privacyCaption: some View {
        Text(model.usePrivateMemories ? "Private memories may inform this reply." : "Private memories stay out of replies.")
            .font(.caption2).foregroundStyle(ThoughtPinsTheme.inkSoft)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func toggleRecording() {
        if voiceRecorder.isRecording {
            finishVoiceRecording()
        } else if voiceDisclosureAccepted {
            Task { await voiceRecorder.start() }
        } else {
            showingVoiceDisclosure = true
        }
    }

    private func finishVoiceRecording() {
        if let data = voiceRecorder.stop() {
            Task { await model.uploadVoiceNote(data) }
        }
    }

    private func submit() {
        let payload = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !payload.isEmpty, !model.isThinking else { return }
        lastQuestion = payload
        text = ""
        // Put the keyboard away. It covers roughly half the screen, which is
        // where the answer is about to appear, and nothing else on this screen
        // dismisses it -- a person had to swipe the field away to read the
        // reply they just asked for.
        composerFocused = false
        Task {
            await model.sendChat(payload)
            if model.bannerIsProblem { lastQuestion = "" }
        }
    }
}
