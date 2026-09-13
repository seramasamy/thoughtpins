import XCTest

extension XCUIApplication {
    func waitForThoughtPinsPasswordKeyboard(timeout: TimeInterval = 20) -> XCTWaiter.Result {
        let password = secureTextFields["Password"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
            // The email keyboard also has an "a" key. Its presence does not
            // mean UIKit has finished installing the password input session.
            // Injecting an entire string during that transition can lose all
            // but its first character. Wait for this field's Go keyboard and
            // a usable accessibility frame before sending any input.
            password.exists && password.frame.minY.isFinite && password.isHittable
                && self.keyboards.buttons["Go"].isHittable
                && self.keyboards.keys["a"].isHittable
        }, object: password)
        return XCTWaiter.wait(for: [ready], timeout: timeout)
    }
}
