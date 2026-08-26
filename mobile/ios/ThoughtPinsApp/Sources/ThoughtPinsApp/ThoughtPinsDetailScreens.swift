import SwiftUI
import ThoughtPinsCore

// The read-only detail screens behind a memory card and a library source.
// Split out of ThoughtPinsScreens.swift when that file reached its size
// budget; these two are one feature and share nothing with the tab screens
// beyond the model.

/// What the app has stored about one person, place or thing.
///
/// Read-only. `memoryCard(id:)` and every model it decodes already existed in
/// ThoughtPinsCore with no caller — the App Store description promises "open a
/// person and see what you have said about them and when you last spoke", and
/// tapping a card did nothing, which is an accurate-metadata problem as much as
/// a missing screen.
///
/// The detail payload also carries salience_score, salience_tier and friends.
/// They are internal ranking values, `MemoryCardDetailResponse` does not decode
/// them, and nothing here should ever show them.
struct ThoughtPinsMemoryCardScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    let card: MemoryCardResponse

    @State private var detail: MemoryCardDetailResponse?
    @State private var failure: String?

    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(detail?.name ?? card.name)
                        .font(.system(.title2, design: .serif).weight(.semibold))
                    if let subtitle = detail?.subtitle ?? card.subtitle, !subtitle.isEmpty {
                        Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
                    }
                    Text(thoughtPinsCardCounts(detail: detail, card: card))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 2)
            }

            if let failure {
                Section {
                    Text(failure).font(.footnote).foregroundStyle(.secondary)
                    Button("Try again") { Task { await load() } }
                }
            } else if detail == nil {
                Section { ProgressView("Loading") }
            }

            if let detail {
                if let lastSeen = detail.lastSeen, !lastSeen.isEmpty {
                    Section("Last mentioned") { Text(lastSeen) }
                }
                if !detail.recentMemories.isEmpty {
                    Section("What you've said") {
                        ForEach(Array(detail.recentMemories.enumerated()), id: \.offset) { _, memory in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(memory.text).font(.body)
                                if let date = memory.date, !date.isEmpty {
                                    Text(date).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }
                if !detail.relationships.isEmpty {
                    Section("Connected to") {
                        ForEach(Array(detail.relationships.enumerated()), id: \.offset) { _, link in
                            LabeledContent(link.other, value: thoughtPinsRelationshipLabel(link.type))
                        }
                    }
                }
                if !detail.timeline.isEmpty {
                    Section("Timeline") {
                        ForEach(Array(detail.timeline.enumerated()), id: \.offset) { _, moment in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(moment.label).font(.subheadline)
                                if let date = moment.date, !date.isEmpty {
                                    Text(date).font(.caption2).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                if !detail.sourceDocuments.isEmpty {
                    Section("From your readings") {
                        ForEach(detail.sourceDocuments, id: \.id) { source in
                            Text(source.title).font(.subheadline)
                        }
                    }
                }
            }
        }
        .thoughtPinsReadableColumn()
        .navigationTitle(card.name)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        failure = nil
        do {
            detail = try await model.api.memoryCard(id: card.id)
        } catch {
            failure = "Could not load this card. Check your connection and try again."
        }
    }
}

/// Inflection markup only resolves inside a `LocalizedStringKey` literal.
/// Returning a `String` and handing it to `Text` printed
/// "^[3 memory](inflect: true)" on screen verbatim, which the detail-view
/// acceptance test caught.
private func thoughtPinsCardCounts(detail: MemoryCardDetailResponse?, card: MemoryCardResponse) -> String {
    let memories = detail?.memoryCount ?? card.memoryCount
    let links = detail?.relationshipCount ?? card.relationshipCount
    let memoryWord = memories == 1 ? "memory" : "memories"
    let linkWord = links == 1 ? "link" : "links"
    return "\(memories) \(memoryWord), \(links) \(linkWord)"
}

/// Relationship kinds come from the database `relation_type` column, so a
/// person saw "Priya — works_on" and "The Ferry Building — located_at".
func thoughtPinsRelationshipLabel(_ relationType: String) -> String {
    switch relationType {
    case "knows": return "Knows"
    case "met_at": return "Met at"
    case "works_on": return "Works on"
    case "works_at": return "Works at"
    case "located_at": return "Located at"
    case "lives_in": return "Lives in"
    case "part_of": return "Part of"
    case "related_to": return "Related to"
    case "mentioned_with": return "Mentioned with"
    default:
        // Anything new the server starts emitting still reads as words.
        return relationType
            .replacingOccurrences(of: "_", with: " ")
            .prefix(1).uppercased()
            + relationType.replacingOccurrences(of: "_", with: " ").dropFirst()
    }
}

/// A saved reading, with where it came from and on what basis.
struct ThoughtPinsLibrarySourceScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    let source: LibrarySourceResponse

    @State private var detail: LibrarySourceResponse?
    @State private var failure: String?

    private var shown: LibrarySourceResponse { detail ?? source }

    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(shown.title).font(.system(.title3, design: .serif).weight(.semibold))
                    if let byline = [shown.author, shown.publisher ?? shown.sourceDomain, shown.publishedAt]
                        .compactMap({ $0 }).filter({ !$0.isEmpty }).first {
                        Text(byline).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 2)
            }
            if let failure {
                Section {
                    Text(failure).font(.footnote).foregroundStyle(.secondary)
                    Button("Try again") { Task { await load() } }
                }
            }
            if let summary = shown.summary, !summary.isEmpty {
                Section("Summary") { Text(summary) }
            }
            if let concepts = shown.keyConcepts, !concepts.isEmpty {
                Section("Key ideas") {
                    ForEach(concepts, id: \.self) { Text($0) }
                }
            }
            Section("About this reading") {
                LabeledContent("Saved sections", value: String(shown.chunks))
                if shown.paywallDetected {
                    Text("This page was behind a paywall, so only its public details were saved.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            if let url = thoughtPinsSourceURL(shown) {
                Section { Link("Open original", destination: url) }
            }
        }
        .thoughtPinsReadableColumn()
        .navigationTitle("Reading")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        failure = nil
        do {
            detail = try await model.api.librarySource(sourceRef: source.id)
        } catch {
            failure = "Could not load the full details. Showing what is already on this device."
        }
    }
}
