import SwiftUI
import ThoughtPinsCore

/// Shown when the server says this build is below the minimum it supports.
///
/// This is the recovery lever for a v1 that ships broken: raise
/// `MIN_IOS_VERSION` above the bad build and every copy of it says so instead
/// of failing in whatever way it fails. `evaluateClientVersion` had existed in
/// ThoughtPinsCore from the start with no caller, so the server could publish a
/// minimum and no device would ever act on it.
///
/// Three rules it has to keep:
///
/// 1. Say what happened in words, not a status code. Someone here has done
///    nothing wrong and cannot fix anything except by updating.
/// 2. Offer a route forward. The App Store link comes from the server
///    (`store_urls.ios`), so it stays right even if the listing moves. If the
///    server has not set one, say plainly where to go rather than showing a
///    button that does nothing.
/// 3. Never trap anyone. Sign out stays reachable, so a person can leave the
///    account on a device they are handing on, and drafts held on the device
///    are named rather than silently stranded.
struct ThoughtPinsUpdateRequiredView: View {
    @ObservedObject var model: ThoughtPinsAppModel

    private var decision: ClientVersionDecision? { model.versionDecision }

    var body: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 0)

            Image(systemName: "arrow.down.circle")
                .font(.system(size: 44))
                .foregroundStyle(ThoughtPinsTheme.brand)
                .accessibilityHidden(true)

            Text("Update Thought Pins to continue")
                .font(.system(.title2, design: .serif).weight(.semibold))
                .multilineTextAlignment(.center)

            Text("This version can no longer talk to Thought Pins safely. "
                + "Updating takes a moment and everything you have saved is waiting.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if let decision {
                Text("You have \(ThoughtPinsAppModel.runningVersion). The oldest supported version is \(decision.minimum).")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .accessibilityIdentifier("thoughtpins-update-versions")
            }

            if let raw = decision?.storeURL, let url = URL(string: raw) {
                Link(destination: url) {
                    Text("Open the App Store")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(ThoughtPinsTheme.brand)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .accessibilityIdentifier("thoughtpins-update-store-link")
            } else {
                // A button that cannot work is worse than a sentence that can.
                Text("Search for Thought Pins in the App Store to update.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("thoughtpins-update-no-link")
            }

            if model.draftCount > 0 {
                Text("^[\(model.draftCount) note](inflect: true) saved on this device will send after you update.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer(minLength: 0)

            if model.isAuthenticated {
                Button("Sign out") { Task { await model.logout() } }
                    .font(.footnote)
                    .accessibilityIdentifier("thoughtpins-update-sign-out")
            }
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemGroupedBackground))
        .thoughtPinsReadableColumn()
        .accessibilityIdentifier("thoughtpins-update-required")
    }
}
