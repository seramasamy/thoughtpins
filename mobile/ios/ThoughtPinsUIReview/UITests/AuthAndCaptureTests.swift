import XCTest

final class AuthAndCaptureTests: XCTestCase {
    private func configure(_ failures: [String: [Int]] = [:], delays: [String: Int] = [:]) throws {
        let done = expectation(description: "Configure fictional API")
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8877/__review")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["failures": failures, "delays": delays])
        URLSession.shared.dataTask(with: request) { _, response, error in
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 5)
    }

    override func tearDownWithError() throws { try configure() }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<14 where !element.isHittable {
            let down = element.exists && element.frame.maxY < app.frame.midY
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.4 : 0.7))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.65 : 0.45))
            start.press(forDuration: 0.05, thenDragTo: end)
        }
        XCTAssertTrue(element.isHittable)
    }

    private func shot(_ name: String) {
        let item = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        item.name = name; item.lifetime = .keepAlways; add(item)
    }

    private func dismissKeyboard(in app: XCUIApplication) {
        app.buttons["Dismiss keyboard"].tap()
        let hidden = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch
        )
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
    }

    private func signedOutApp(accessibility: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = accessibility ? ["--accessibility-review"] : []
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 20))
        app.buttons["Account"].firstMatch.tap()
        let signOut = app.buttons["Sign out"]
        reveal(signOut, in: app); signOut.tap()
        XCTAssertTrue(app.secureTextFields["Password"].waitForExistence(timeout: 5))
        return app
    }

    func testSignInValidationPasswordVisibilityAndRecovery() throws {
        try configure(["POST /v1/auth/login": [401, 429]], delays: ["POST /v1/auth/login": 2000])
        let app = signedOutApp()
        shot("Auth-sign-in")
        let email = app.textFields["Email"]
        reveal(email, in: app); email.tap(); email.typeText("   ")
        let password = app.secureTextFields["Password"]
        password.tap(); password.typeText("fictional password only")
        let submit = app.buttons["thoughtpins-auth-submit"]
        XCTAssertFalse(submit.isEnabled)
        app.buttons["Show password"].tap()
        XCTAssertEqual(app.textFields["Password"].value as? String, "fictional password only")
        app.buttons["Hide password"].tap()
        XCTAssertTrue(app.secureTextFields["Password"].exists)
        email.tap(); email.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 3) + "review@example.com")
        dismissKeyboard(in: app)
        for _ in 0..<2 {
            reveal(submit, in: app); submit.tap()
            XCTAssertTrue(app.staticTexts["thoughtpins-auth-progress"].waitForExistence(timeout: 3))
            XCTAssertFalse(submit.isEnabled)
            let retry = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: submit)
            XCTAssertEqual(XCTWaiter.wait(for: [retry], timeout: 10), .completed)
            XCTAssertEqual(email.value as? String, "review@example.com")
            shot("Auth-retry")
        }
        submit.tap()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 15))
    }

    func testSignupAndPhoneKeyboardAtLargestTextSize() throws {
        try configure()
        let app = signedOutApp(accessibility: true)
        let create = app.buttons["Create account"].firstMatch
        reveal(create, in: app); create.tap()
        let usePhone = app.buttons["Use phone"]
        reveal(usePhone, in: app); usePhone.tap()
        let phone = app.textFields["Phone"]
        reveal(phone, in: app); phone.tap(); phone.typeText("+15555550123")
        dismissKeyboard(in: app)
        let password = app.secureTextFields["Password"]
        reveal(password, in: app); password.tap(); password.typeText("short")
        dismissKeyboard(in: app)
        let submit = app.buttons["thoughtpins-auth-submit"]
        reveal(submit, in: app); XCTAssertFalse(submit.isEnabled)
        XCTAssertTrue(app.staticTexts["Choose a password of at least 12 characters."].exists)
        shot("Auth-create-account-accessibility")
        let consent = app.switches.firstMatch
        reveal(consent, in: app); XCTAssertTrue(consent.isHittable)
        let privacy = app.links["Privacy"]
        // SwiftUI Link is exposed as a button on some simulator versions.
        let legal = privacy.exists ? privacy : app.buttons["Privacy"]
        reveal(legal, in: app); shot("Auth-legal-accessibility")
    }

    func testFailedLinkRetainsDraftAndCaptureCanGoBack() throws {
        try configure(["POST /v1/library": [503]])
        let app = XCUIApplication(); app.launch()
        XCTAssertTrue(app.tabBars.buttons["Pins"].waitForExistence(timeout: 20))
        app.tabBars.buttons["Pins"].tap(); app.buttons["Add a pin"].tap()
        let link = app.textFields["Article link"]
        reveal(link, in: app); link.tap(); link.typeText("https://example.com/fictional")
        dismissKeyboard(in: app)
        let submit = app.buttons["thoughtpins-link-import"]
        reveal(submit, in: app); submit.tap()
        XCTAssertTrue(app.staticTexts["Could not import that link. It is still here so you can try again."].waitForExistence(timeout: 10))
        XCTAssertEqual(link.value as? String, "https://example.com/fictional")
        shot("Capture-link-recovery")
        submit.tap()
        let cleared = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "https://..."), object: link)
        XCTAssertEqual(XCTWaiter.wait(for: [cleared], timeout: 10), .completed)
        let back = app.navigationBars.buttons["Pins"].firstMatch
        XCTAssertTrue(back.isHittable); back.tap()
        XCTAssertTrue(app.buttons["Add a pin"].isHittable)
    }
}
