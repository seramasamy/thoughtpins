import Foundation
import AuthenticationServices
import AVFoundation
import SwiftUI
import ThoughtPinsCore
import UIKit
import UniformTypeIdentifiers

struct ThoughtPinsRecapScreen: View {
    @ObservedObject var model: ThoughtPinsAppModel
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var showingCapture = false
    @State private var period = "Day"
    @State private var pendingDeletion: EntryResponse?

    private var summaryLayout: AnyLayout {
        dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(spacing: 16)) : AnyLayout(HStackLayout(spacing: 0))
    }

    var body: some View {
        NavigationStack {
            List {
                VStack(alignment: .leading, spacing: 24) {
                    ThoughtPinsPageIntro(eyebrow: "Your life, in view", title: period == "Day" ? "A moment to\nlook back." : "See the bigger\npicture.",
                                         detail: Date.now.formatted(.dateTime.weekday(.wide).month(.wide).day()), symbol: "sun.max")
                    Picker("Recap period", selection: $period) {
                        Text("Day").tag("Day")
                        Text("Week").tag("Week")
                        Text("Month").tag("Month")
                    }
                    .pickerStyle(.segmented)
                    summaryLayout {
                        summaryNumber(filteredEntries.count, label: "Entries", symbol: "text.alignleft")
                        Divider().frame(height: dynamicTypeSize.isAccessibilitySize ? 1 : 40)
                        summaryNumber(model.memoryCards.count, label: "People", symbol: "person.2")
                        Divider().frame(height: dynamicTypeSize.isAccessibilitySize ? 1 : 40)
                        summaryNumber(model.librarySources.count, label: "Pins", symbol: "pin")
                    }
                    .thoughtPinsCard(padding: 18)
                    HStack {
                        Text("Your journal").font(.title3.weight(.semibold))
                        Spacer()
                        Button { showingCapture = true } label: {
                            Label("Add a note", systemImage: "plus").font(.subheadline.weight(.medium))
                                .frame(minHeight: 44)
                        }
                        .buttonStyle(.borderless)
                    }
                }
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
                .listRowInsets(EdgeInsets(top: 18, leading: 20, bottom: 14, trailing: 20))

                if filteredEntries.isEmpty {
                    ThoughtPinsEmptyState("Nothing here yet", detail: "Entries you save this \(period.lowercased()) will appear here.",
                                          actionTitle: "Write your first note", destination: AnyView(ThoughtPinsCaptureScreen(model: model)))
                        .listRowBackground(Color.clear).listRowSeparator(.hidden)
                }
                ForEach(filteredEntries, id: \.id) { entry in
                    VStack(alignment: .leading, spacing: 16) {
                        HStack(spacing: 8) {
                            Image(systemName: "circle.fill").font(.system(size: 6)).foregroundStyle(ThoughtPinsTheme.brand)
                            Text(entry.localDate ?? String(entry.createdAtUtc.prefix(10)))
                                .font(.caption.weight(.medium)).foregroundStyle(ThoughtPinsTheme.inkSoft)
                            Spacer()
                            Image(systemName: "text.alignleft").font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                        }
                        Text(entry.rawText).font(.body).lineSpacing(5).foregroundStyle(ThoughtPinsTheme.ink)
                        HStack {
                            Label("Journal", systemImage: "book.closed").font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                            Spacer()
                            Menu {
                                ForEach(1...5, id: \.self) { rating in
                                    Button {
                                        Task { await model.updateEntryImportance(entryId: entry.id, value: rating) }
                                    } label: {
                                        Label("Set importance to \(rating) out of 5", systemImage: rating == entry.userImportance ? "star.fill" : "star")
                                    }
                                }
                                if entry.userImportance != nil {
                                    Button("Clear importance rating") {
                                        Task { await model.updateEntryImportance(entryId: entry.id, value: nil) }
                                    }
                                }
                            } label: {
                                Label(entry.userImportance.map { "\($0) / 5" } ?? "Rate", systemImage: entry.userImportance == nil ? "star" : "star.fill")
                                    .font(.caption.weight(.medium)).frame(minWidth: 44, minHeight: 44)
                            }
                            .buttonStyle(.borderless)
                            .accessibilityLabel("Importance rating")
                            .accessibilityValue(entry.userImportance.map { "\($0) out of 5" } ?? "Not rated")
                        }
                    }
                    .thoughtPinsCard()
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(top: 6, leading: 20, bottom: 6, trailing: 20))
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) { pendingDeletion = entry } label: { Label("Delete", systemImage: "trash") }
                            .accessibilityIdentifier("thoughtpins-delete-entry")
                    }
                    .contextMenu {
                        Button(role: .destructive) { pendingDeletion = entry } label: { Label("Delete entry", systemImage: "trash") }
                    }
                }
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .thoughtPinsReadableColumn(maxWidth: 800)
            .thoughtPinsScreen()
            .refreshable { await model.refreshReadModels() }
            .navigationTitle("Recap")
            .navigationDestination(isPresented: $showingCapture) { ThoughtPinsCaptureScreen(model: model) }
            .toolbar { ThoughtPinsAccountToolbar(model: model) }
            .confirmationDialog("Delete this entry?", isPresented: Binding(get: { pendingDeletion != nil }, set: { if !$0 { pendingDeletion = nil } }), titleVisibility: .visible) {
                Button("Delete entry", role: .destructive) {
                    if let entry = pendingDeletion {
                        pendingDeletion = nil
                        Task { await model.deleteEntry(id: entry.id) }
                    }
                }
                Button("Keep it", role: .cancel) { pendingDeletion = nil }
            } message: {
                Text("This removes the entry, anything remembered from it, and any recording kept for it. It cannot be undone.")
            }
        }
    }

    private func summaryNumber(_ count: Int, label: String, symbol: String) -> some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                HStack(spacing: 18) {
                    Text(count.formatted()).font(.title.weight(.semibold)).foregroundStyle(ThoughtPinsTheme.ink)
                    Text(label).font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                    Spacer(minLength: 0)
                }
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Image(systemName: symbol).font(.subheadline).foregroundStyle(ThoughtPinsTheme.accent)
                    Text(count.formatted()).font(.system(.title, design: .rounded).weight(.semibold)).foregroundStyle(ThoughtPinsTheme.ink)
                    Text(label).font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
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
