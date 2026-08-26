import SwiftUI
import UIKit

/// Warm-paper design tokens for the iOS shell, mirroring DESIGN.md.
/// Colors are dynamic: exact brand values in light, softened in dark,
/// matching the Android Compose palette.
enum ThoughtPinsTheme {
    /// #E8612B in light, #E8895F in dark.
    static let brand = dynamic(light: (0.9098, 0.3804, 0.1686), dark: (0.9098, 0.5373, 0.3725))
    /// #B33E16 in light, #E8895F in dark.
    static let action = dynamic(light: (0.7020, 0.2431, 0.0863), dark: (0.9098, 0.5373, 0.3725))
    /// #FBE9DD in light, #402518 in dark.
    static let brandSoft = dynamic(light: (0.9843, 0.9137, 0.8667), dark: (0.2510, 0.1451, 0.0941))
    /// #F8F8F6 in light, #1A1714 in dark.
    static let canvas = dynamic(light: (0.9725, 0.9725, 0.9647), dark: (0.1020, 0.0902, 0.0784))
    /// #FFFFFF in light, #221D18 in dark.
    static let surface = dynamic(light: (1.0, 1.0, 1.0), dark: (0.1333, 0.1137, 0.0941))
    /// #E6E2DD in light, #383128 in dark.
    static let line = dynamic(light: (0.9020, 0.8863, 0.8667), dark: (0.2196, 0.1922, 0.1569))
    /// #6B6459 in light, #B5AC9F in dark.
    static let inkSoft = dynamic(light: (0.4196, 0.3922, 0.3490), dark: (0.7098, 0.6745, 0.6235))
    /// #26211B — constant charcoal band.
    static let charcoal = Color(red: 0.1490, green: 0.1294, blue: 0.1059)

    static func dynamic(light: (Double, Double, Double), dark: (Double, Double, Double)) -> Color {
        Color(UIColor { traits in
            let components = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: components.0, green: components.1, blue: components.2, alpha: 1)
        })
    }
}

/// The three-dot thinking motif: model or indexing work, never decoration.
/// Falls back to static dots when Reduce Motion is on.
struct ThoughtPinsThinkingDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var animating = false

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(ThoughtPinsTheme.inkSoft)
                    .frame(width: 6, height: 6)
                    .opacity(animating ? 1.0 : 0.25)
                    .animation(
                        reduceMotion
                            ? nil
                            : .easeInOut(duration: 0.6)
                                .repeatForever(autoreverses: true)
                                .delay(Double(index) * 0.16),
                        value: animating
                    )
            }
        }
        .onAppear { animating = true }
        .accessibilityHidden(true)
    }
}

/// Branded empty state: quiet mark, serif line, one supporting sentence.
struct ThoughtPinsEmptyState: View {
    let title: String
    var detail: String?
    /// Somewhere to go. Every one of these screens fills up as a consequence of
    /// writing something, so an empty one that only explains itself leaves a
    /// new account reading a description of a thing it cannot reach from here.
    var action: (title: String, destination: AnyView)?

    init(_ title: String, detail: String? = nil) {
        self.title = title
        self.detail = detail
        self.action = nil
    }

    init(_ title: String, detail: String? = nil, actionTitle: String, destination: AnyView) {
        self.title = title
        self.detail = detail
        self.action = (actionTitle, destination)
    }

    var body: some View {
        VStack(spacing: 10) {
            ThoughtPinsBrandMark()
                .frame(width: 44, height: 44)
                .opacity(0.3)
            Text(title)
                .font(.system(.headline, design: .serif))
                .accessibilityAddTraits(.isHeader)
            if let detail {
                Text(detail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            if let action {
                NavigationLink { action.destination } label: {
                    Text(action.title)
                }
                .buttonStyle(.borderedProminent)
                .tint(ThoughtPinsTheme.brand)
                .padding(.top, 4)
                .accessibilityIdentifier("thoughtpins-empty-action")
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 36)
        // Combined only when there is nothing to tap; otherwise the button has
        // to stay its own element for VoiceOver.
        .accessibilityElement(children: action == nil ? .combine : .contain)
    }
}

/// Holds content to a comfortable reading measure and centres it.
///
/// Every screen here was laid out for a phone. On a 12.9" iPad that gives the
/// chat column a ~1000pt line of body text — roughly 150 characters, about
/// twice the measure text stays readable at — and it strands the switch of a
/// Toggle row an inch and a half from the label it belongs to. The app claims
/// universal (`TARGETED_DEVICE_FAMILY: "1,2"`), so it gets opened on iPad.
///
/// Only regular width is constrained. Every iPhone, and an iPad in Slide Over
/// or a narrow Split View, stays compact and is left exactly as it was.
struct ThoughtPinsReadableColumn: ViewModifier {
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    let maxWidth: CGFloat

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: horizontalSizeClass == .regular ? maxWidth : .infinity)
            .frame(maxWidth: .infinity)
    }
}

extension View {
    /// - Parameter maxWidth: 680pt holds body text near 75 characters, the wide
    ///   end of what stays comfortable to read.
    func thoughtPinsReadableColumn(maxWidth: CGFloat = 680) -> some View {
        modifier(ThoughtPinsReadableColumn(maxWidth: maxWidth))
    }
}
