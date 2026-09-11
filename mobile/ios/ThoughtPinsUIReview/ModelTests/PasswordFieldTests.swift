import SwiftUI
import UIKit
import XCTest
@testable import ThoughtPinsApp

final class PasswordFieldTests: XCTestCase {
    @MainActor func testTypingAndDeletingAfterConcealmentKeepExistingText() {
        let field = ThoughtPinsPasswordTextField()
        field.configure(text: "fictional", revealed: false, fontSize: 17)
        field.selectedTextRange = field.textRange(from: field.endOfDocument, to: field.endOfDocument)
        field.configure(text: "fictional", revealed: true, fontSize: 17)
        field.configure(text: "fictional", revealed: false, fontSize: 17)
        field.insertText("a")
        XCTAssertEqual(field.text, "fictionala")
        XCTAssertEqual(field.offset(from: field.beginningOfDocument, to: field.selectedTextRange!.start), 10)
        field.deleteBackward()
        XCTAssertEqual(field.text, "fictional")
    }

    @MainActor func testVisibilityPreservesTheWholePasswordAndSelection() {
        let field = ThoughtPinsPasswordTextField()
        let sample = "  Fictional 🧭 e\u{301} password  "
        field.configure(text: sample, revealed: false, fontSize: 17)
        let caret = field.position(from: field.beginningOfDocument, offset: 5)!
        field.selectedTextRange = field.textRange(from: caret, to: caret)
        for revealed in [true, false, true, false] {
            field.configure(text: sample, revealed: revealed, fontSize: 53)
            XCTAssertEqual(field.text, sample)
            XCTAssertEqual(field.isSecureTextEntry, !revealed)
            XCTAssertEqual(field.offset(from: field.beginningOfDocument, to: field.selectedTextRange!.start), 5)
        }
        XCTAssertEqual(field.textContentType, .password)
        XCTAssertNil(field.passwordRules)
        XCTAssertEqual(field.font?.pointSize, 53)
        field.insertText("X")
        XCTAssertEqual(field.text, (sample as NSString).replacingCharacters(in: NSRange(location: 5, length: 0), with: "X"))
        field.configure(text: sample, revealed: false, fontSize: 17)
        XCTAssertEqual(field.text, sample)
        XCTAssertEqual(field.textContentType, .password)
        XCTAssertNil(field.passwordRules)
    }

    @MainActor func testEditingAndReturnPublishExactTextBeforeSubmitting() {
        var password = ""
        var focused = false
        var submitted: String?
        let input = ThoughtPinsPasswordInput(
            text: Binding(get: { password }, set: { password = $0 }),
            isFocused: Binding(get: { focused }, set: { focused = $0 }),
            revealed: false, fontSize: 17,
            submit: { submitted = password }
        )
        let coordinator = input.makeCoordinator()
        let field = ThoughtPinsPasswordTextField()
        coordinator.textFieldDidBeginEditing(field)
        XCTAssertTrue(focused)
        field.text = "  fictional exact password 🧭  "
        coordinator.changed(field)
        XCTAssertEqual(password, field.text)
        field.text = "fictional replacement from AutoFill"
        XCTAssertFalse(coordinator.textFieldShouldReturn(field))
        XCTAssertEqual(submitted, field.text)
        coordinator.dismissKeyboard()
        XCTAssertFalse(focused)
        coordinator.textFieldDidEndEditing(field)
        XCTAssertEqual(password, field.text)
    }
}
