import SwiftUI

struct ThoughtPinsPasswordField: View {
    @Binding var text: String
    var creatingAccount: Bool
    @FocusState.Binding var isFocused: Bool
    var submit: () -> Void
    @State private var revealed = false

    var body: some View {
        HStack(spacing: 4) {
            Group {
                if revealed {
                    TextField("Password", text: $text)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                } else {
                    SecureField("Password", text: $text)
                }
            }
            .textContentType(creatingAccount ? .newPassword : .password)
            .focused($isFocused).submitLabel(.go).onSubmit(submit)
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
