import SwiftUI
import ThoughtPinsCore

struct ThoughtPinsMemoryScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    let cards: [MemoryCardResponse]
    let title: String
    @State private var query = ""
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var isPlace: Bool { title == "Places" }
    private var shown: [MemoryCardResponse] {
        guard !query.isEmpty else { return cards }
        return cards.filter { $0.name.localizedCaseInsensitiveContains(query) || ($0.subtitle ?? "").localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    ThoughtPinsPageIntro(
                        eyebrow: isPlace ? "Your personal atlas" : "Your inner circle",
                        title: isPlace ? "Every place.\nA part of your story." : "Life is better\nconnected.",
                        detail: isPlace ? "The places, moments, and details that stay with you." : "The people in your life, remembered through the moments you share.",
                        symbol: isPlace ? "mappin.and.ellipse" : "person.2"
                    )
                    ThoughtPinsSearchField(placeholder: "Search \(title.lowercased())", text: $query)
                    if cards.isEmpty {
                        ThoughtPinsEmptyState(
                            "No \(title.lowercased()) yet",
                            detail: "People and places from your journal become connected cards here.",
                            actionTitle: "Write your first note",
                            destination: AnyView(ThoughtPinsCaptureScreen(model: model))
                        )
                    } else if shown.isEmpty {
                        ThoughtPinsEmptyState("No matches", detail: "Try another name or detail.")
                    } else {
                        HStack {
                            Text("\(shown.count) \(shown.count == 1 ? (isPlace ? "place" : "person") : title.lowercased())").font(.subheadline.weight(.medium))
                            Spacer()
                            Image(systemName: "square.grid.2x2").foregroundStyle(ThoughtPinsTheme.inkSoft)
                        }
                        LazyVGrid(columns: dynamicTypeSize.isAccessibilitySize ? [GridItem(.flexible())] : [GridItem(.adaptive(minimum: 280), spacing: 16)], spacing: 16) {
                            ForEach(shown, id: \.id) { card in
                                NavigationLink { ThoughtPinsMemoryCardScreen(model: model, card: card) } label: {
                                    ThoughtPinsMemoryTile(card: card, isPlace: isPlace)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(20).padding(.bottom, 20)
                .thoughtPinsReadableColumn(maxWidth: 980)
            }
            .scrollDismissesKeyboard(.interactively)
            .thoughtPinsScreen()
            .refreshable { await model.refreshReadModels() }
            .navigationTitle(title)
            .toolbar { ThoughtPinsAccountToolbar(model: model) }
        }
    }
}

private struct ThoughtPinsMemoryTile: View {
    let card: MemoryCardResponse
    let isPlace: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(alignment: .top) {
                ZStack {
                    RoundedRectangle(cornerRadius: 17).fill(ThoughtPinsTheme.accentSoft)
                    if isPlace {
                        Image(systemName: "mappin.and.ellipse").font(.system(size: 24))
                    } else {
                        Text(card.name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined())
                            .font(.system(size: 20, weight: .semibold))
                    }
                }
                .foregroundStyle(ThoughtPinsTheme.accent).frame(width: 54, height: 54)
                .accessibilityHidden(true)
                Spacer()
                Image(systemName: "arrow.up.right").font(.subheadline).foregroundStyle(ThoughtPinsTheme.inkSoft)
            }
            VStack(alignment: .leading, spacing: 7) {
                Text(card.name).font(.title3.weight(.semibold)).foregroundStyle(ThoughtPinsTheme.ink)
                if let subtitle = card.subtitle, !subtitle.isEmpty {
                    Text(subtitle).font(.subheadline).foregroundStyle(ThoughtPinsTheme.inkSoft).lineLimit(3)
                }
            }
            Divider().overlay(ThoughtPinsTheme.line)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 18) { counts }
                VStack(alignment: .leading, spacing: 8) { counts }
            }
            .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .thoughtPinsCard()
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var counts: some View {
        Label("\(card.memoryCount) \(card.memoryCount == 1 ? "memory" : "memories")", systemImage: "sparkle")
        Label("\(card.relationshipCount) \(card.relationshipCount == 1 ? "connection" : "connections")", systemImage: "point.3.connected.trianglepath.dotted")
    }
}

struct ThoughtPinsLibraryScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @State private var query = ""
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    private var shown: [LibrarySourceResponse] {
        guard !query.isEmpty else { return model.librarySources }
        return model.librarySources.filter { $0.title.localizedCaseInsensitiveContains(query) || ($0.summary ?? "").localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    ThoughtPinsPageIntro(eyebrow: "Collected by you", title: "Good ideas\ndeserve a place.",
                                         detail: "Your library of links, notes, and things worth coming back to.", symbol: "pin")
                    ThoughtPinsSearchField(placeholder: "Search pins", text: $query)
                    if model.librarySources.isEmpty {
                        ThoughtPinsEmptyState("No sources yet", detail: "Keep a link, a document, or an idea. This is where it all comes together.",
                                              actionTitle: "Save a link or document", destination: AnyView(ThoughtPinsCaptureScreen(model: model)))
                    } else if shown.isEmpty {
                        ThoughtPinsEmptyState("No matches", detail: "Try a different title or phrase.")
                    } else {
                        LazyVGrid(columns: dynamicTypeSize.isAccessibilitySize ? [GridItem(.flexible())] : [GridItem(.adaptive(minimum: 280), spacing: 16)], spacing: 16) {
                            ForEach(shown, id: \.id) { source in
                                NavigationLink { ThoughtPinsLibrarySourceScreen(model: model, source: source) } label: {
                                    VStack(alignment: .leading, spacing: 18) {
                                        HStack {
                                            Image(systemName: "doc.text").font(.system(size: 22)).foregroundStyle(ThoughtPinsTheme.accent)
                                                .frame(width: 50, height: 50).background(ThoughtPinsTheme.accentSoft, in: RoundedRectangle(cornerRadius: 16))
                                            Spacer()
                                            Image(systemName: "arrow.up.right").foregroundStyle(ThoughtPinsTheme.inkSoft)
                                        }
                                        Text(source.title).font(.title3.weight(.semibold)).foregroundStyle(ThoughtPinsTheme.ink)
                                        if let summary = source.summary, !summary.isEmpty {
                                            Text(summary).font(.subheadline).lineLimit(3).foregroundStyle(ThoughtPinsTheme.inkSoft)
                                        }
                                        Divider()
                                        Text([source.publisher ?? source.sourceDomain, "\(source.chunks) memory \(source.chunks == 1 ? "section" : "sections")"]
                                            .compactMap { $0 }.joined(separator: " · "))
                                            .font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading).thoughtPinsCard()
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(20).padding(.bottom, 20).thoughtPinsReadableColumn(maxWidth: 980)
            }
            .scrollDismissesKeyboard(.interactively)
            .thoughtPinsScreen()
            .refreshable { await model.refreshReadModels() }
            .navigationTitle("Pins")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink { ThoughtPinsCaptureScreen(model: model) } label: { Image(systemName: "plus") }
                        .accessibilityLabel("Add a pin")
                }
                ThoughtPinsAccountToolbar(model: model)
            }
        }
    }
}

struct ThoughtPinsAccountToolbar: ToolbarContent {
    @ObservedObject var model: ThoughtPinsAppModel
    var body: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            NavigationLink { ThoughtPinsAccountScreen(model: model) } label: {
                Image(systemName: "person.crop.circle").symbolRenderingMode(.hierarchical)
            }
            .accessibilityLabel("Account")
        }
    }
}
