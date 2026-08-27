import SwiftUI
import UIKit

/// The system share sheet, so an export becomes a file a person keeps.
///
/// SwiftUI's `ShareLink` would be tidier but needs iOS 16+ *and* a `Transferable`;
/// a file URL through `UIActivityViewController` is the smaller, older, more
/// predictable path, and it gives "Save to Files" as well as every share target.
struct ThoughtPinsShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
