import SwiftUI
import ThoughtPinsApp
@main struct ReviewApp: App {
    var body: some Scene {
        WindowGroup { ReviewRoot() }
    }
}

private struct ReviewRoot: View {
    @Environment(\.dynamicTypeSize) private var systemTypeSize
    var body: some View {
        ThoughtPinsRootView(baseURL: URL(string: "http://127.0.0.1:8877")!)
            .dynamicTypeSize(ProcessInfo.processInfo.arguments.contains("--accessibility-review") ? .accessibility5 : systemTypeSize)
    }
}
