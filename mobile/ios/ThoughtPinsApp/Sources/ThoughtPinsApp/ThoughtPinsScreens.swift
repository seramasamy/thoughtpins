import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

struct ThoughtPinsMainShell: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @ObservedObject var voiceRecorder: ThoughtPinsVoiceRecorder

    var body: some View {
        TabView {
            ThoughtPinsRecapScreen(model: model)
                .tabItem { Label("Recap", systemImage: "calendar") }
            ThoughtPinsMemoryScreen(model: model, cards: model.memoryCards, title: "People")
                .tabItem { Label("People", systemImage: "person.2") }
            ThoughtPinsChatScreen(model: model, voiceRecorder: voiceRecorder)
                .tabItem { Label("Chat", systemImage: "ellipsis.message") }
            ThoughtPinsMemoryScreen(model: model, cards: model.placeCards, title: "Places")
                .tabItem { Label("Places", systemImage: "mappin") }
            ThoughtPinsLibraryScreen(model: model)
                .tabItem { Label("Pins", systemImage: "pin") }
        }
        .tint(ThoughtPinsTheme.brand)
    }
}

struct ThoughtPinsRecapScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var period = "Day"

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Recap period", selection: $period) {
                    Text("Day").tag("Day")
                    Text("Week").tag("Week")
                    Text("Month").tag("Month")
                }
                .pickerStyle(.segmented)
                .padding()

                List(filteredEntries, id: \.id) { entry in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(entry.localDate ?? entry.createdAtUtc).font(.caption).foregroundStyle(.secondary)
                        Text(entry.rawText).font(.body)
                        // The label sits above the stars rather than beside
                        // them. Five 44pt targets plus the clear button are
                        // 264pt of fixed width, which leaves nothing for a
                        // caption in a 320pt iPad Slide Over and truncates it
                        // on an iPhone SE.
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Importance").font(.caption).foregroundStyle(.secondary)
                            HStack(spacing: 2) {
                                ForEach(1...5, id: \.self) { rating in
                                    Button {
                                        Task { await model.updateEntryImportance(entryId: entry.id, value: rating) }
                                    } label: {
                                        Image(systemName: rating <= (entry.userImportance ?? 0) ? "star.fill" : "star")
                                            .foregroundStyle(rating <= (entry.userImportance ?? 0) ? ThoughtPinsTheme.brand : Color.secondary)
                                            .frame(width: 44, height: 44)
                                            // A plain button hit-tests its label's
                                            // glyph, not the frame around it, so
                                            // these were 17pt targets wearing a
                                            // 44pt box until this line.
                                            .contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel("Set importance to \(rating) out of 5")
                                }
                                if entry.userImportance != nil {
                                    Button {
                                        Task { await model.updateEntryImportance(entryId: entry.id, value: nil) }
                                    } label: {
                                        Image(systemName: "xmark")
                                            .frame(width: 44, height: 44)
                                            .contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel("Clear importance rating")
                                }
                                Spacer(minLength: 0)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
                .refreshable { await model.refreshReadModels() }
                .overlay {
                    if filteredEntries.isEmpty {
                        ThoughtPinsEmptyState(
                            "Nothing here yet",
                            detail: "Entries you save this \(period.lowercased()) will appear here.",
                            actionTitle: "Write your first note",
                            destination: AnyView(ThoughtPinsCaptureScreen(model: model))
                        )
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Recap")
            .toolbar { accountToolbar }
        }
    }

    private var filteredEntries: [EntryResponse] {
        let calendar = Calendar.current
        let now = Date()
        return model.recentEntries.filter { entry in
            guard let raw = entry.localDate ?? entry.createdAtUtc.split(separator: "T").first.map(String.init),
                  let date = DateFormatter.thoughtPinsDay.date(from: raw) else { return true }
            if period == "Day" { return calendar.isDate(date, inSameDayAs: now) }
            if period == "Week" { return calendar.isDate(date, equalTo: now, toGranularity: .weekOfYear) }
            return calendar.isDate(date, equalTo: now, toGranularity: .month)
        }
    }

    @ToolbarContentBuilder private var accountToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            NavigationLink { ThoughtPinsAccountScreen(model: model) } label: { Image(systemName: "person.crop.circle") }
        }
    }
}

struct ThoughtPinsChatScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @ObservedObject var voiceRecorder: ThoughtPinsVoiceRecorder
    @State private var text = ""
    @State private var showingVoiceDisclosure = false
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("thoughtpins.voiceDisclosure.2026-07-13") private var voiceDisclosureAccepted = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @FocusState private var composerFocused: Bool
    @State private var showingReportDialog = false

    private var composerLayout: AnyLayout {
        dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .bottom, spacing: 8))
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Toggle("Use private memories", isOn: Binding(
                        get: { model.usePrivateMemories },
                        set: { model.setUsePrivateMemories($0) }
                    ))
                    .accessibilityHint("When off, private memories stay out of this reply.")
                    Text(model.usePrivateMemories
                        ? "Private memories may inform this reply."
                        : "Private memories stay out of replies.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        // Without this the line is truncated to "Private
                        // memories…" at the accessibility sizes: SwiftUI gives
                        // the transcript below the remaining height and clips
                        // this instead of wrapping it.
                        .fixedSize(horizontal: false, vertical: true)
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        if !model.chatReply.isEmpty, let route = thoughtPinsRouteLabel(model.routeLabel) {
                            Text(route.uppercased())
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(ThoughtPinsTheme.inkSoft)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(ThoughtPinsTheme.brandSoft, in: Capsule())
                        }
                        if model.chatReply.isEmpty {
                            ThoughtPinsEmptyState(
                                "Ask Thought Pins anything",
                                detail: "Normal language routes to chat, journal, search, article import, or account actions."
                            )
                            .padding(.top, 24)
                        } else {
                            ThoughtPinsReplyView(reply: model.chatReply)
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
                        if !model.chatReply.isEmpty {
                            Button {
                                showingReportDialog = true
                            } label: {
                                Label("Report this reply", systemImage: "flag")
                                    .font(.caption)
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(ThoughtPinsTheme.inkSoft)
                            .padding(.horizontal, 4)
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
                    .animation(.easeInOut(duration: 0.22), value: model.chatReply)
                    .animation(.easeInOut(duration: 0.22), value: model.isThinking)
                }
                .scrollDismissesKeyboard(.interactively)
                // At the accessibility text sizes the mic, the field and Send
                // cannot share a row: the field collapses to about two visible
                // characters and Send is pushed against the screen edge. Stack
                // them instead once the type is that large.
                composerLayout {
                    Button {
                        if voiceRecorder.isRecording {
                            finishVoiceRecording()
                        } else {
                            if voiceDisclosureAccepted {
                                Task { await voiceRecorder.start() }
                            } else {
                                showingVoiceDisclosure = true
                            }
                        }
                    } label: {
                        Image(systemName: voiceRecorder.isRecording ? "stop.circle.fill" : "mic.fill")
                            .frame(width: 44, height: 44)
                            .symbolEffect(.pulse, options: .repeating, isActive: voiceRecorder.isRecording)
                    }
                    .buttonStyle(.bordered)
                    .tint(voiceRecorder.isRecording ? .red : ThoughtPinsTheme.brand)
                    .accessibilityLabel(voiceRecorder.isRecording ? "Stop voice note" : "Record a voice note")
                    .accessibilityHint("Records a voice note and saves it to your journal.")
                    TextField("Talk normally", text: $text, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .submitLabel(.send)
                        .onSubmit(submit)
                        .disabled(model.isThinking)
                        .focused($composerFocused)
                    Button("Send", action: submit)
                        .disabled(model.isThinking || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        // The keyboard's return key also carries a "Send"
                        // accessibility label, because the field sets
                        // submitLabel(.send). Without an identifier the two are
                        // indistinguishable to anything driving the app.
                        .accessibilityIdentifier("thoughtpins-chat-send")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
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
            .thoughtPinsReadableColumn()
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
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { ThoughtPinsAccountScreen(model: model) } label: { Image(systemName: "person.crop.circle") }
                }
            }
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

    private func finishVoiceRecording() {
        if let data = voiceRecorder.stop() {
            Task { await model.uploadVoiceNote(data) }
        }
    }

    private func submit() {
        let payload = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !payload.isEmpty, !model.isThinking else { return }
        text = ""
        // Put the keyboard away. It covers roughly half the screen, which is
        // where the answer is about to appear, and nothing else on this screen
        // dismisses it -- a person had to swipe the field away to read the
        // reply they just asked for.
        composerFocused = false
        Task { await model.sendChat(payload) }
    }
}

struct ThoughtPinsCaptureScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var journalText = ""
    @State private var link = ""
    @State private var uploadDestination: ThoughtPinsUploadDestination = .auto

    var body: some View {
        NavigationStack {
            Form {
                Section("Journal") {
                    TextEditor(text: $journalText).frame(minHeight: 160)
                    Button("Save journal") {
                        let payload = journalText
                        journalText = ""
                        Task { await model.saveJournal(payload) }
                    }
                }
                Section("Article or document link") {
                    TextField("https://...", text: $link)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                    Button("Import link") {
                        let payload = link
                        link = ""
                        Task { await model.ingestLink(payload) }
                    }
                }
                Section("Add a file") {
                    Picker("Destination", selection: $uploadDestination) {
                        ForEach(ThoughtPinsUploadDestination.allCases) { destination in
                            Text(destination.label).tag(destination)
                        }
                    }
                    Button("Choose file to import") {
                        Task { await model.uploadSelectedFile(destination: uploadDestination) }
                    }
                    Text("Choose Obsidian Vault for a vault ZIP. Other files use the selected journal or library destination.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let transfer = model.pendingVaultImport, let preview = transfer.result {
                    Section("Vault preview") {
                        Text("\(preview.newNotes) new, \(preview.changedNotes) changed, \(preview.unchangedNotes) unchanged")
                        Text("\(preview.journalNotes) journal notes and \(preview.libraryNotes) library notes")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button("Apply import") {
                            Task { await model.applyPendingVaultImport() }
                        }
                        Button("Discard preview", role: .destructive) {
                            Task { await model.discardPendingVaultImport() }
                        }
                    }
                }
                if model.draftCount > 0 {
                    Section("Offline drafts") {
                        Text("\(model.draftCount) queued")
                        Button("Sync queued drafts") { Task { try? await model.syncDrafts() } }
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Capture")
        }
    }
}

struct ThoughtPinsLibraryScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel

    var body: some View {
        NavigationStack {
            List(model.librarySources, id: \.id) { source in
                NavigationLink {
                    ThoughtPinsLibrarySourceScreen(model: model, source: source)
                } label: {
                VStack(alignment: .leading, spacing: 5) {
                    Text(source.title).font(.system(.headline, design: .serif))
                    Text([
                        source.publisher ?? source.sourceDomain,
                        source.publishedAt,
                        "\(source.chunks) memory \(source.chunks == 1 ? "section" : "sections")"
                    ].compactMap { $0 }.joined(separator: " | "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let summary = source.summary, !summary.isEmpty {
                        Text(summary)
                            .font(.subheadline)
                            .lineLimit(3)
                    }
                }
                .padding(.vertical, 4)
                }
            }
            .refreshable { await model.refreshReadModels() }
            .overlay {
                if model.librarySources.isEmpty {
                    ThoughtPinsEmptyState(
                        "No sources yet",
                        detail: "Links and documents you save will appear here with their source details.",
                        actionTitle: "Save a link or document",
                        destination: AnyView(ThoughtPinsCaptureScreen(model: model))
                    )
                }
            }
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Pins")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { ThoughtPinsCaptureScreen(model: model) } label: { Image(systemName: "plus") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { ThoughtPinsAccountScreen(model: model) } label: { Image(systemName: "person.crop.circle") }
                }
            }
        }
    }

}

struct ThoughtPinsMemoryScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    let cards: [MemoryCardResponse]
    let title: String

    var body: some View {
        NavigationStack {
            List(cards, id: \.id) { card in
                NavigationLink {
                    ThoughtPinsMemoryCardScreen(model: model, card: card)
                } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(card.name).font(.system(.headline, design: .serif))
                    Text(card.subtitle ?? card.type).font(.subheadline)
                    // "1 memories | 2 links" read wrong on a card with a
                    // single memory, and VoiceOver announced the pipe.
                    Text("^[\(card.memoryCount) memory](inflect: true), ^[\(card.relationshipCount) link](inflect: true)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let path = card.obsidianPath {
                        Text("Archive: \(thoughtPinsReferenceTitle(path, fallback: card.name))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                }
            }
            // Hide the List's own backdrop first: once the list is narrower
            // than the window it would otherwise draw a visible band down the
            // middle of the screen with a hard edge on either side.
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .refreshable { await model.refreshReadModels() }
            .overlay {
                if cards.isEmpty {
                    ThoughtPinsEmptyState(
                        "No \(title.lowercased()) yet",
                        detail: "People and places from your journal become connected cards here.",
                        actionTitle: "Write your first note",
                        destination: AnyView(ThoughtPinsCaptureScreen(model: model))
                    )
                }
            }
            .navigationTitle(title)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { ThoughtPinsAccountScreen(model: model) } label: { Image(systemName: "person.crop.circle") }
                }
            }
        }
    }
}

private extension DateFormatter {
    static let thoughtPinsDay: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}

struct ThoughtPinsAccountScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var showingDeleteConfirmation = false
    @State private var showingVoiceConsent = false
    @State private var showingVoiceDeleteConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Signed in") {
                    Text(model.me?.email ?? model.me?.phone ?? "Thought Pins account")
                }
                Section("Data") {
                    Button("Export account") { Task { await model.exportAccount() } }
                    Button("Delete account", role: .destructive) { showingDeleteConfirmation = true }
                }
                if model.config?.voiceArchiveEnabled == true {
                    Section("Personal voice archive") {
                        if let status = model.voiceArchiveStatus {
                            LabeledContent("Retention", value: status.enabled ? "On" : "Off")
                            LabeledContent("Recordings", value: String(status.assetCount))
                            LabeledContent("Original size", value: thoughtPinsByteCount(status.originalBytes))
                            Text("Voice notes are transcribed and discarded by default. Enabling the archive retains encrypted recordings for future features built only for your account.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if status.enabled {
                                Button("Stop future retention") { Task { await model.disableVoiceArchive() } }
                            } else {
                                Button("Review and enable") { showingVoiceConsent = true }
                            }
                            if status.assetCount > 0 {
                                Button("Delete retained recordings", role: .destructive) {
                                    showingVoiceDeleteConfirmation = true
                                }
                            }
                        } else {
                            ProgressView("Loading voice archive")
                        }
                    }
                }
                Section("Response voice") {
                    Picker("Voice", selection: Binding(
                        get: { model.responseStyle },
                        set: { style in Task { await model.updateResponseStyle(style) } }
                    )) {
                        Text("Friendly").tag("friendly")
                        Text("Clear").tag("clear")
                        Text("Match me").tag("mirror")
                    }
                    .pickerStyle(.segmented)
                    Text("Friendly is warm and professional. Matching your style is always an explicit choice.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Journal importance") {
                    Toggle("Occasional rating prompts", isOn: Binding(
                        get: { model.importancePromptsEnabled },
                        set: { enabled in Task { await model.updateImportancePrompts(enabled) } }
                    ))
                    Text("Prompts are optional and only appear after substantial saves.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Legal and support") {
                    Link("Privacy Policy", destination: model.legalURL(configured: model.config?.privacyPolicyUrl, fallbackPath: "/privacy"))
                    Link("Terms", destination: model.legalURL(configured: model.config?.termsUrl, fallbackPath: "/terms"))
                    Link("Support", destination: model.legalURL(configured: model.config?.supportUrl, fallbackPath: "/support"))
                    Link("Account Deletion", destination: model.legalURL(configured: model.config?.accountDeletionUrl, fallbackPath: "/account/delete"))
                    Link("AI Disclosure", destination: model.legalURL(configured: model.config?.aiDisclosureUrl, fallbackPath: "/ai-disclosure"))
                    Text(model.aiProcessingConsentAccepted ? "AI processing permission is active." : "AI processing permission is not active.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Session") {
                    Button("Sign out") { Task { await model.logout() } }
                }
            }
            // Held to a readable measure on iPad for the same reason as
            // every other screen: at 1024pt a Toggle strands its switch an
            // inch and a half from its label, and this one is the screen a
            // reviewer opens for 5.1.1(v). Backdrop hidden first so the
            // narrowed content does not draw a band with hard edges.
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Account")
            .confirmationDialog(
                "Permanently delete your Thought Pins account and saved data?",
                isPresented: $showingDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete account", role: .destructive) { Task { await model.deleteAccount() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Export anything you want to keep first. This action cannot be undone.")
            }
            .confirmationDialog(
                "Delete all retained voice recordings?",
                isPresented: $showingVoiceDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete voice archive", role: .destructive) { Task { await model.deleteVoiceArchive() } }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Encrypted audio and future derived voice data are removed. Journal transcripts remain until you delete their entries or your account.")
            }
            .sheet(isPresented: $showingVoiceConsent) {
                ThoughtPinsVoiceArchiveConsentView(model: model, isPresented: $showingVoiceConsent)
            }
        }
    }
}

private struct ThoughtPinsVoiceArchiveConsentView: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @Binding var isPresented: Bool
    @State private var retainRecordings = false
    @State private var sensitiveAudio = false
    @State private var personalUseOnly = false
    @State private var deletionAvailable = false

    private var confirmed: Bool {
        retainRecordings && sensitiveAudio && personalUseOnly && deletionAvailable
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Review before enabling") {
                    Text("Voice recordings can identify you. Thought Pins will retain them only for features built for your account, never for a shared model or another user's model.")
                    Toggle("Retain future recordings after transcription", isOn: $retainRecordings)
                    Toggle("I understand voice audio is sensitive and identifying", isOn: $sensitiveAudio)
                    Toggle("Use recordings only for my personal voice features", isOn: $personalUseOnly)
                    Toggle("I can disable retention or delete the archive at any time", isOn: $deletionAvailable)
                }
                Section("Private recall") {
                    Toggle("Use private memories in replies by default", isOn: Binding(
                        get: { model.usePrivateMemories },
                        set: { enabled in Task { await model.updatePrivateRecallDefault(enabled) } }
                    ))
                    Text("Off by default. Private memories stay out of recall unless you explicitly enable them. This setting does not mark new messages private.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn()
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Voice archive")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { isPresented = false }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Enable") {
                        isPresented = false
                        Task { await model.enableVoiceArchive() }
                    }
                    .disabled(!confirmed)
                }
            }
        }
    }
}

private func thoughtPinsByteCount(_ bytes: Int) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
}

// Not file-private: the library list and the source detail screen both need it.
func thoughtPinsSourceURL(_ source: LibrarySourceResponse) -> URL? {
    [source.canonicalUrl, source.sourceUrl, source.originalUrl]
        .compactMap { $0 }
        .compactMap(URL.init(string:))
        .first { ["http", "https"].contains($0.scheme?.lowercased() ?? "") }
}

private func thoughtPinsReferenceTitle(_ path: String, fallback: String) -> String {
    let leaf = path.split(whereSeparator: { $0 == "/" || $0 == "\\" }).last.map(String.init) ?? ""
    let title = leaf.hasSuffix(".md") ? String(leaf.dropLast(3)) : leaf
    return title.isEmpty ? fallback : title
}
