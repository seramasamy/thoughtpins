import SwiftUI
import UIKit

/// Mineral surfaces and ember accents, shared with the web visual system.
/// The established brand tint is retained; surfaces have explicit light and
/// dark values. Filled actions use a separate color for readable white labels.
enum ThoughtPinsTheme {
    /// #E8612B in light, #E8895F in dark.
    static let brand = dynamic(light: (0.9098, 0.3804, 0.1686), dark: (0.9098, 0.5373, 0.3725))
    /// #B33E16 in light, #E8895F in dark.
    static let action = dynamic(light: (0.7020, 0.2431, 0.0863), dark: (0.9098, 0.5373, 0.3725))
    static let brandSoft = dynamic(light: (1.0, 0.9412, 0.9098), dark: (0.2196, 0.1529, 0.1216))
    static let canvas = dynamic(light: (0.9569, 0.9608, 0.9765), dark: (0.0471, 0.0706, 0.1255))
    static let surface = dynamic(light: (1.0, 1.0, 1.0), dark: (0.0824, 0.1176, 0.1882))
    static let line = dynamic(light: (0.8784, 0.8941, 0.9333), dark: (0.1647, 0.2078, 0.2941))
    static let ink = dynamic(light: (0.0980, 0.1294, 0.1961), dark: (0.9294, 0.9490, 1.0))
    static let inkSoft = dynamic(light: (0.3804, 0.4196, 0.4980), dark: (0.6627, 0.7098, 0.7961))
    static let accent = dynamic(light: (0.3294, 0.3294, 0.7216), dark: (0.6745, 0.6588, 1.0))
    static let accentSoft = dynamic(light: (0.9333, 0.9294, 0.9843), dark: (0.1569, 0.1569, 0.2863))
    static let charcoal = Color(red: 0.0745, green: 0.1059, blue: 0.1686)
    /// White labels retain contrast in both appearances.
    static let buttonFill = Color(red: 0.7020, green: 0.2431, blue: 0.0863)

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

/// Branded empty state: quiet mark, clear heading, one supporting sentence.
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
            ThoughtPinsOrbit(size: 92)
            Text(title)
                .font(.system(.title3, design: .default).weight(.semibold))
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
                .buttonStyle(ThoughtPinsPrimaryStyle())
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
