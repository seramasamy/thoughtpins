import SwiftUI
import ThoughtPinsApp

@main
struct ThoughtPinsNativeApp: App {
    private let apiBaseURL: URL = {
        let configured = Bundle.main.object(forInfoDictionaryKey: "THOUGHTPINS_API_BASE_URL") as? String
        return URL(string: configured ?? "https://api.thoughtpins.com")!
    }()

    var body: some Scene {
        WindowGroup {
            ThoughtPinsRootView(
                baseURL: apiBaseURL,
                oauthTokenProvider: GoogleOAuthTokenProvider()
            )
            .onOpenURL { url in
                _ = GoogleOAuthTokenProvider.handle(url)
            }
        }
    }
}
