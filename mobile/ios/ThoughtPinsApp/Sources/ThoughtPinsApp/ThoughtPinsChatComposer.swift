import SwiftUI

struct ThoughtPinsChatComposer: View {
    @Binding var text: String
    @FocusState.Binding var focused: Bool
    let busy: Bool
    let recording: Bool
    let record: () -> Void
    let submit: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var canSend: Bool { !busy && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if typeSize.isAccessibilitySize { input }
            HStack(alignment: .bottom, spacing: 8) {
                Button(action: record) {
                    Image(systemName: recording ? "stop.circle.fill" : "mic.fill")
                        .font(.system(size: 19))
                        .frame(width: 44, height: 44)
                        .symbolEffect(.pulse, options: .repeating, isActive: recording && !reduceMotion)
                }
                .buttonStyle(.plain)
                .foregroundStyle(recording ? Color.red : ThoughtPinsTheme.inkSoft)
                .accessibilityLabel(recording ? "Stop voice note" : "Record a voice note")
                .accessibilityHint("Records a voice note and saves it to your journal.")
                if typeSize.isAccessibilitySize { Spacer() } else { input }
                Button(action: submit) {
                    Image(systemName: "arrow.up").font(.system(size: 18, weight: .semibold))
                        .frame(width: 44, height: 44)
                        .foregroundStyle(.white)
                        .background(ThoughtPinsTheme.buttonFill, in: Circle())
                }
                .accessibilityLabel("Send")
                .accessibilityIdentifier("thoughtpins-chat-send")
                .disabled(!canSend)
                .opacity(canSend ? 1 : 0.45)
            }
        }
        .padding(8)
        .background(ThoughtPinsTheme.surface, in: RoundedRectangle(cornerRadius: 24))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(ThoughtPinsTheme.line, lineWidth: 1))
    }

    private var input: some View {
        TextField(typeSize.isAccessibilitySize ? "Message" : "Message Thought Pins", text: $text, axis: .vertical)
            .textFieldStyle(.plain)
            .lineLimit(1...(typeSize.isAccessibilitySize ? 2 : 6))
            .padding(.vertical, 12)
            .accessibilityLabel("Message Thought Pins")
            .accessibilityIdentifier("thoughtpins-chat-input")
            .submitLabel(.send)
            .onSubmit(submit)
            .disabled(busy)
            .focused($focused)
    }
}
