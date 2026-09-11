import SwiftUI

struct ThoughtPinsCaptureScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var journalText = ""
    @State private var link = ""
    @FocusState private var focusedField: Field?
    private enum Field { case journal, link }
    @State private var uploadDestination: ThoughtPinsUploadDestination = .auto

    var body: some View {
        Form {
            Section("Journal") {
                TextEditor(text: $journalText).frame(minHeight: 180)
                    .scrollContentBackground(.hidden)
                    .accessibilityLabel("Journal note")
                    .focused($focusedField, equals: .journal)
                Text("A moment, an idea, or something you want to remember.")
                    .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                Button(model.savingJournal ? "Saving…" : "Save journal") {
                    let payload = journalText
                    Task {
                        if await model.saveJournal(payload), journalText == payload {
                            journalText = ""
                            focusedField = nil
                        }
                    }
                }
                .disabled(model.savingJournal || journalText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityIdentifier("thoughtpins-journal-save")
            }
            Section("Article or document link") {
                TextField("https://...", text: $link)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                    .focused($focusedField, equals: .link)
                    .accessibilityLabel("Article link")
                Button(model.importingLink ? "Importing…" : "Import link") {
                    let payload = link
                    Task {
                        if await model.ingestLink(payload), link == payload {
                            link = ""
                            focusedField = nil
                        }
                    }
                }
                .disabled(model.importingLink || link.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityIdentifier("thoughtpins-link-import")
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
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }
                    .accessibilityLabel("Dismiss keyboard")
            }
        }
    }
}
