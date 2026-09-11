import SwiftUI

struct ThoughtPinsChatWelcome: View {
    let choose: (String) -> Void
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        VStack(spacing: 12) {
            ThoughtPinsOrbit(size: sizeClass == .regular ? 132 : 84).padding(.bottom, 4)
            Text("A LITTLE SPACE FOR YOUR MIND")
                .font(.system(.caption2).weight(.semibold)).tracking(1.6)
                .foregroundStyle(ThoughtPinsTheme.inkSoft)
            Text("What is on your mind?")
                .font(.system(.title, design: .default).weight(.bold)).tracking(-0.8)
                .foregroundStyle(ThoughtPinsTheme.ink).multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            Text("A thought, a moment, a question.\nStart anywhere. Make a connection.")
                .font(.subheadline).lineSpacing(4).multilineTextAlignment(.center)
                .foregroundStyle(ThoughtPinsTheme.inkSoft)
            VStack(spacing: 10) {
                starter("Find a thread", prompt: "What has been on my mind?", symbol: "lightbulb")
                starter("Take a moment", prompt: "Help me reflect on this week", symbol: "sparkles")
                starter("Reconnect", prompt: "Who have I mentioned lately?", symbol: "person.2")
            }
            .padding(.top, 10)
        }
        .frame(maxWidth: 500)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
    }

    private func starter(_ title: String, prompt: String, symbol: String) -> some View {
        Button { choose(prompt) } label: {
            HStack(spacing: 14) {
                Image(systemName: symbol).font(.system(size: 20)).foregroundStyle(ThoughtPinsTheme.accent).frame(width: 24)
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(ThoughtPinsTheme.ink)
                    Text(prompt).font(.caption).foregroundStyle(ThoughtPinsTheme.inkSoft)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "arrow.up.right").font(.system(size: 12)).foregroundStyle(ThoughtPinsTheme.inkSoft)
            }
            .thoughtPinsCard(padding: 14)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(prompt)
    }
}
