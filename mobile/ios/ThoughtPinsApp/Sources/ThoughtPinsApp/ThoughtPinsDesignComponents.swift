import SwiftUI

struct ThoughtPinsPageIntro: View {
    let eyebrow: String
    let title: String
    let detail: String
    var symbol: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                if let symbol { Image(systemName: symbol) }
                Text(eyebrow.uppercased()).tracking(1.5)
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(ThoughtPinsTheme.accent)
            Text(title)
                .font(.system(.largeTitle, design: .default).weight(.bold))
                .tracking(-0.8)
                .foregroundStyle(ThoughtPinsTheme.ink)
                .accessibilityAddTraits(.isHeader)
            Text(detail).font(.subheadline).foregroundStyle(ThoughtPinsTheme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct ThoughtPinsCardSurface: ViewModifier {
    var padding: CGFloat = 20
    func body(content: Content) -> some View {
        content.padding(padding)
            .background(ThoughtPinsTheme.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(ThoughtPinsTheme.line, lineWidth: 1))
    }
}

struct ThoughtPinsScreenSurface: ViewModifier {
    func body(content: Content) -> some View {
        content
            .scrollContentBackground(.hidden)
            .background {
                ThoughtPinsTheme.canvas.ignoresSafeArea()
                LinearGradient(colors: [ThoughtPinsTheme.accentSoft.opacity(0.55), .clear],
                               startPoint: .topTrailing, endPoint: .center)
                    .ignoresSafeArea().allowsHitTesting(false)
            }
            .toolbarBackground(ThoughtPinsTheme.canvas, for: .navigationBar)
            .navigationBarTitleDisplayMode(.inline)
    }
}

struct ThoughtPinsPrimaryStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .frame(maxWidth: .infinity, minHeight: 52)
            .foregroundStyle(.white)
            .background(ThoughtPinsTheme.buttonFill, in: RoundedRectangle(cornerRadius: 17, style: .continuous))
            .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.16), value: configuration.isPressed)
    }
}

struct ThoughtPinsSearchField: View {
    let placeholder: String
    @Binding var text: String
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").foregroundStyle(ThoughtPinsTheme.inkSoft)
            TextField(placeholder, text: $text)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .accessibilityLabel(placeholder)
                .focused($focused)
                .submitLabel(.search)
                .onSubmit { focused = false }
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill").frame(width: 44, height: 44)
                }
                .accessibilityLabel("Clear search")
                .foregroundStyle(ThoughtPinsTheme.inkSoft)
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52)
        .background(ThoughtPinsTheme.surface, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(ThoughtPinsTheme.line, lineWidth: 1))
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focused = false }
            }
        }
    }
}

extension View {
    func thoughtPinsCard(padding: CGFloat = 20) -> some View {
        modifier(ThoughtPinsCardSurface(padding: padding))
    }
    func thoughtPinsScreen() -> some View { modifier(ThoughtPinsScreenSurface()) }
}
