import XCTest

final class AuthAndCaptureTests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    private func configure(_ failures: [String: [Int]] = [:], delays: [String: Int] = [:]) throws {
        let done = expectation(description: "Configure fictional API")
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8877/__review")!)
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["failures": failures, "delays": delays])
        URLSession.shared.dataTask(with: request) { _, response, error in
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            done.fulfill()
        }.resume()
        // A freshly booted CI simulator can take several seconds to initialize
        // its first URLSession connection. This is fixture setup, not app latency.
        wait(for: [done], timeout: 20)
    }

    override func tearDownWithError() throws { try configure() }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<14 where !element.isHittable {
            // Keep the gesture inside the form when a keyboard covers the
            // lower screen. Dragging the keyboard cannot reveal a form field.
            let keyboard = app.keyboards.firstMatch
            let visibleHeight = keyboard.exists
                ? min(app.frame.height, keyboard.frame.minY - app.frame.minY) : app.frame.height
            let fraction = visibleHeight / app.frame.height
            let down = element.exists && element.frame.maxY < app.frame.minY + visibleHeight / 2
            let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: fraction * (down ? 0.4 : 0.7)))
            let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: fraction * (down ? 0.65 : 0.45)))
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

    private func waitForPasswordKeyboard(in app: XCUIApplication) {
        // Password AutoFill can delay the software keyboard on the simulator.
        // Sending keys before it appears can enter just one letter.
        let ready = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "hittable == true"), object: app.keyboards.keys["a"]
        )
        let result = XCTWaiter.wait(for: [ready], timeout: 20)
        if result != .completed { shot("Auth-keyboard-unavailable") }
        XCTAssertEqual(result, .completed)
    }

    private func signedOutApp(accessibility: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = accessibility ? ["--accessibility-review"] : []
        app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        app.buttons["Account"].firstMatch.tap()
        let signOut = app.buttons["Sign out"]
        reveal(signOut, in: app); signOut.tap()
        XCTAssertTrue(app.secureTextFields["Password"].waitForExistence(timeout: 5))
        return app
    }

    func testNativeTabNavigationAndTabletLandscape() throws {
        try configure()
        let app = XCUIApplication(); app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        let tablet = app.frame.width >= 700
        defer { XCUIDevice.shared.orientation = .portrait }
        for landscape in tablet ? [false, true] : [false] {
            if landscape {
                XCUIDevice.shared.orientation = .landscapeLeft
                let rotated = XCTNSPredicateExpectation(
                    predicate: NSPredicate { _, _ in app.frame.width > app.frame.height }, object: app
                )
                XCTAssertEqual(XCTWaiter.wait(for: [rotated], timeout: 5), .completed)
            }
            for name in ["Recap", "People", "Chat", "Places", "Pins"] {
                let tab = app.thoughtPinsTab(name)
                XCTAssertTrue(tab.isHittable); tab.tap()
                XCTAssertTrue(app.navigationBars[name].waitForExistence(timeout: 5))
                shot("Navigation-\(name)-\(landscape ? "landscape" : "portrait")")
            }
        }
    }

    func testSignInValidationPasswordVisibilityAndRecovery() throws {
        try configure(["POST /v1/auth/login": [401, 429]], delays: ["POST /v1/auth/login": 2000])
        let app = signedOutApp()
        shot("Auth-sign-in")
        let email = app.textFields["Email"]
        reveal(email, in: app); email.tap(); email.typeText("   ")
        let password = app.secureTextFields["Password"]
        reveal(password, in: app); password.tap(); waitForPasswordKeyboard(in: app)
        password.typeText("fictional password only")
        let submit = app.buttons["thoughtpins-auth-submit"]
        XCTAssertFalse(submit.isEnabled)
        app.buttons["Show password"].tap()
        XCTAssertEqual(app.textFields["Password"].value as? String, "fictional password only")
        app.buttons["Hide password"].tap()
        XCTAssertTrue(app.secureTextFields["Password"].exists)
        app.keys["a"].tap()
        app.buttons["Show password"].tap()
        XCTAssertEqual(app.textFields["Password"].value as? String, "fictional password onlya")
        app.buttons["Hide password"].tap()
        reveal(email, in: app); email.tap()
        email.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 3) + "review@example.com")
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
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 15))
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
        reveal(password, in: app); password.tap(); waitForPasswordKeyboard(in: app)
        password.typeText("short")
        dismissKeyboard(in: app)
        let submit = app.buttons["thoughtpins-auth-submit"]
        reveal(submit, in: app); XCTAssertFalse(submit.isEnabled)
        XCTAssertTrue(app.staticTexts["Choose a password of at least 12 characters."].exists)
        let show = app.buttons["Show password"]
        reveal(show, in: app); show.tap()
        XCTAssertEqual(app.textFields["Password"].value as? String, "short")
        shot("Auth-create-account-accessibility")
        let consent = app.switches.firstMatch
        reveal(consent, in: app); XCTAssertTrue(consent.isHittable)
        let privacy = app.links["Privacy"]
        // SwiftUI Link is exposed as a button on some simulator versions.
        let legal = privacy.exists ? privacy : app.buttons["Privacy"]
        reveal(legal, in: app); shot("Auth-legal-accessibility")
    }

    func testCreateAccountCompletesAfterConsent() throws {
        try configure()
        let app = signedOutApp()
        app.buttons["Create account"].firstMatch.tap()
        let email = app.textFields["Email"]
        reveal(email, in: app); email.tap(); email.typeText("new-review@example.com\n")
        let password = app.secureTextFields["Password"]
        let focused = XCTNSPredicateExpectation(predicate: NSPredicate(format: "hittable == true"), object: password)
        XCTAssertEqual(XCTWaiter.wait(for: [focused], timeout: 5), .completed)
        waitForPasswordKeyboard(in: app)
        password.typeText("fictional password only")
        app.buttons["Show password"].tap()
        XCTAssertEqual(app.textFields["Password"].value as? String, "fictional password only")
        app.buttons["Hide password"].tap()
        dismissKeyboard(in: app)
        let submit = app.buttons["thoughtpins-auth-submit"]
        reveal(submit, in: app); XCTAssertFalse(submit.isEnabled)
        let consent = app.switches.firstMatch
        reveal(consent, in: app)
        // SwiftUI exposes the label and switch as one element. Hit the actual
        // trailing switch, then verify its state before attempting signup.
        consent.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        XCTAssertEqual(consent.value as? String, "1")
        reveal(submit, in: app); XCTAssertTrue(submit.isEnabled)
        shot("Auth-registration-ready")
        submit.tap()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        shot("Auth-registration-complete")
    }

    func testFailedLinkRetainsDraftAndCaptureCanGoBack() throws {
        try configure(["POST /v1/library": [503]])
        let app = XCUIApplication(); app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Pins").waitForExistence(timeout: 20))
        app.thoughtPinsTab("Pins").tap(); app.buttons["Add a pin"].tap()
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
        let returned = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "hittable == true"), object: app.buttons["Add a pin"]
        )
        XCTAssertEqual(XCTWaiter.wait(for: [returned], timeout: 5), .completed)
    }
}
