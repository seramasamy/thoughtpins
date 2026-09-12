import SwiftUI

/// Work feedback owns its animation lifetime. No repeating implicit animation
/// survives a Reduce Motion change, a disappeared view, or an inactive scene.
struct ThoughtPinsThinkingDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var visible = false
    @State private var started = Date()

    private var active: Bool { visible && !reduceMotion && scenePhase == .active }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: !active)) { context in
            let time = context.date.timeIntervalSince(started)
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { index in
                    Circle().fill(ThoughtPinsTheme.inkSoft).frame(width: 6, height: 6)
                        .opacity(active ? 0.65 + 0.3 * sin(time * 3.5 - Double(index) * 0.7) : 0.65)
                }
            }
        }
        .onAppear { started = Date(); visible = true }
        .onDisappear { visible = false }
        .accessibilityHidden(true)
    }
}
