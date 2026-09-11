import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

struct ThoughtPinsCaptureScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var journalText = ""
    @State private var link = ""
    @State private var uploadDestination: ThoughtPinsUploadDestination = .auto

    var body: some View {
        NavigationStack {
            Form {
                Section("Journal") {
                    TextEditor(text: $journalText).frame(minHeight: 180)
                        .scrollContentBackground(.hidden)
                        .accessibilityLabel("Journal note")
                    Text("A moment, an idea, or something you want to remember.")
                        .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                    Button("Save journal") {
                        let payload = journalText
                        journalText = ""
                        Task { await model.saveJournal(payload) }
                    }
                    .disabled(journalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
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
                if model.vaultImportPhase != .idle {
                    Section("Vault import") {
                        HStack(spacing: 10) {
                            ProgressView()
                            Text(model.vaultImportPhase == .applying
                                ? "Importing your vault. This can take a few minutes for a large vault."
                                : "Reading your vault. This can take a few minutes for a large vault.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Button("Cancel", role: .destructive) {
                            model.cancelVaultImportInProgress()
                        }
                        .accessibilityIdentifier("thoughtpins-vault-cancel")
                    }
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
            .thoughtPinsScreen()
            .navigationTitle("Capture")
        }
    }
}

struct ThoughtPinsAccountScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var showingDeleteConfirmation = false
    @State private var showingVoiceConsent = false
    @State private var showingVoiceDeleteConfirmation = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 16) {
                        Image(systemName: "person.crop.circle.fill")
                            .font(.system(size: 48)).symbolRenderingMode(.hierarchical)
                            .foregroundStyle(ThoughtPinsTheme.accent)
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Your space").font(.title2.weight(.semibold))
                            Text(model.me?.email ?? model.me?.phone ?? "Thought Pins account")
                                .font(.subheadline).foregroundStyle(ThoughtPinsTheme.inkSoft)
                            Text("Make Thought Pins yours.").font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                        }
                    }
                    .padding(.vertical, 10)
                }
                Section("Data") {
                    Button("Export account") { Task { await model.exportAccount() } }
                    if model.exportedFile != nil {
                        Text("Your export is a JSON file. Save it to Files, or send it to yourself.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
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
            .thoughtPinsScreen()
            // Without this the export was fetched and dropped on the floor.
            .sheet(isPresented: Binding(
                get: { model.exportedFile != nil },
                set: { if !$0 { model.exportedFile = nil } }
            )) {
                if let file = model.exportedFile {
                    ThoughtPinsShareSheet(items: [file])
                }
            }
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
            .thoughtPinsScreen()
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
