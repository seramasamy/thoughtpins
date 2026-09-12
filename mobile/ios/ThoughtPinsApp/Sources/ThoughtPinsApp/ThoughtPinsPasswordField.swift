import SwiftUI
import UIKit

struct ThoughtPinsPasswordField: View {
    @Binding var text: String
    @Binding var isFocused: Bool
    var submit: () -> Void
    @State private var revealed = false
    @ScaledMetric(relativeTo: .body) private var fontSize: CGFloat = 17

    var body: some View {
        HStack(spacing: 4) {
            ThoughtPinsPasswordInput(
                text: $text, isFocused: $isFocused,
                revealed: revealed, fontSize: fontSize, submit: submit
            )
            .frame(height: max(44, fontSize * 1.3))
            Button {
                revealed.toggle()
            } label: {
                Image(systemName: revealed ? "eye.slash" : "eye")
                    .font(.system(size: 20, weight: .medium))
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(revealed ? "Hide password" : "Show password")
        }
        .padding(.leading, 15).padding(.trailing, 4).padding(.vertical, 4)
        .background(ThoughtPinsTheme.canvas, in: RoundedRectangle(cornerRadius: 14))
    }
}

/// Keep one input alive while changing visibility. Replacing a SwiftUI
/// SecureField with a TextField also replaces the system's AutoFill input.
struct ThoughtPinsPasswordInput: UIViewRepresentable {
    @Binding var text: String
    @Binding var isFocused: Bool
    var revealed: Bool
    var fontSize: CGFloat
    var submit: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> ThoughtPinsPasswordTextField {
        let field = ThoughtPinsPasswordTextField()
        field.placeholder = "Password"
        field.accessibilityLabel = "Password"
        field.autocapitalizationType = .none
        field.autocorrectionType = .no
        field.spellCheckingType = .no
        field.returnKeyType = .go
        field.delegate = context.coordinator
        field.addTarget(context.coordinator, action: #selector(Coordinator.changed(_:)), for: .editingChanged)
        field.setContentHuggingPriority(.defaultLow, for: .horizontal)
        field.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let toolbar = UIToolbar()
        let done = UIBarButtonItem(title: "Done", style: .done, target: context.coordinator,
                                  action: #selector(Coordinator.dismissKeyboard))
        done.accessibilityLabel = "Dismiss keyboard"
        toolbar.items = [UIBarButtonItem(systemItem: .flexibleSpace), done]
        toolbar.sizeToFit()
        field.inputAccessoryView = toolbar
        return field
    }

    func updateUIView(_ field: ThoughtPinsPasswordTextField, context: Context) {
        context.coordinator.parent = self
        field.configure(text: text, revealed: revealed, fontSize: fontSize)
        context.coordinator.updateInteraction(field, isEnabled: context.environment.isEnabled)
    }

    static func dismantleUIView(_ field: ThoughtPinsPasswordTextField, coordinator: Coordinator) {
        coordinator.cancelInteractionUpdate()
        field.delegate = nil
    }

    final class Coordinator: NSObject, UITextFieldDelegate {
        var parent: ThoughtPinsPasswordInput
        private var interactionRevision = 0
        init(_ parent: ThoughtPinsPasswordInput) { self.parent = parent }

        func cancelInteractionUpdate() { interactionRevision += 1 }

        func updateInteraction(_ field: ThoughtPinsPasswordTextField, isEnabled: Bool) {
            interactionRevision += 1
            let revision = interactionRevision
            // Disabling an active UITextField resigns first responder. Doing
            // that inside updateUIView re-enters SwiftUI's focus graph and can
            // deadlock keyboard submission. Apply both changes after the render
            // transaction; a newer update or dismantle invalidates stale work.
            DispatchQueue.main.async { [weak self, weak field] in
                guard let self, let field, revision == self.interactionRevision else { return }
                if field.isEnabled != isEnabled { field.isEnabled = isEnabled }
                if self.parent.isFocused && isEnabled {
                    if field.window != nil && !field.isFirstResponder { field.becomeFirstResponder() }
                } else if field.isFirstResponder {
                    field.resignFirstResponder()
                }
            }
        }
        @objc func changed(_ field: UITextField) {
            let value = field.text ?? ""
            if parent.text != value { parent.text = value }
        }
        @objc func dismissKeyboard() { parent.isFocused = false }
        func textFieldDidBeginEditing(_ textField: UITextField) {
            textField.clearsOnInsertion = false
            if !parent.isFocused { parent.isFocused = true }
        }
        func textFieldDidEndEditing(_ textField: UITextField) {
            changed(textField)
            if parent.isFocused { parent.isFocused = false }
        }
        func textFieldShouldReturn(_ textField: UITextField) -> Bool {
            changed(textField)
            parent.submit()
            return false
        }
    }
}

final class ThoughtPinsPasswordTextField: UITextField {
    func configure(text: String, revealed: Bool, fontSize: CGFloat) {
        // This target has no webcredentials association. On iOS 17, requesting
        // automatic password generation can cover the input and block typing.
        // Retain ordinary password AutoFill and exact manual entry instead.
        if textContentType != .password { textContentType = .password }
        if isSecureTextEntry == revealed {
            let selection = selectedTextRange
            isSecureTextEntry = !revealed
            // Rebuild the editing buffer through UIKit's input path. Setting
            // .text alone marks it as a prefilled secret that the next key clears.
            self.text = ""
            if text == "\n" { self.text = text }
            else if !text.isEmpty { super.insertText(text) }
            if let selection { selectedTextRange = selection }
        } else if self.text != text {
            self.text = text
        }
        font = .systemFont(ofSize: fontSize)
        textColor = .label
        clearsOnInsertion = false
    }
}
