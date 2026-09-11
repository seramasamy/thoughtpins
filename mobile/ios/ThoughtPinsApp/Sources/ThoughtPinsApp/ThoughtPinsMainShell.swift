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

    @State private var selectedTab = 2

    var body: some View {
        TabView(selection: $selectedTab) {
            ThoughtPinsRecapScreen(model: model)
                .tabItem { Label("Recap", systemImage: "calendar") }
                .tag(0)
            ThoughtPinsMemoryScreen(model: model, cards: model.memoryCards, title: "People")
                .tabItem { Label("People", systemImage: "person.2") }
                .tag(1)
            ThoughtPinsChatScreen(model: model, voiceRecorder: voiceRecorder)
                .tabItem { Label("Chat", systemImage: "ellipsis.message") }
                .tag(2)
            ThoughtPinsMemoryScreen(model: model, cards: model.placeCards, title: "Places")
                .tabItem { Label("Places", systemImage: "mappin") }
                .tag(3)
            ThoughtPinsLibraryScreen(model: model)
                .tabItem { Label("Pins", systemImage: "pin") }
                .tag(4)
        }
        .tint(ThoughtPinsTheme.action)
        .toolbarBackground(.visible, for: .tabBar)
        .toolbarBackground(.ultraThinMaterial, for: .tabBar)
    }
}
