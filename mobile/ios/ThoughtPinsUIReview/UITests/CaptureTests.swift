import XCTest
final class CaptureTests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    func shot(_ name: String, _ app: XCUIApplication) {
        // App-window crops are offset after rotation on the iOS 17 simulator.
        // Capture the full screen so landscape evidence includes every edge.
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func reveal(_ element: XCUIElement, in app: XCUIApplication, scroller: XCUIElement? = nil) {
        // Small drags avoid skipping a search field at accessibility sizes.
        // Reverse direction if it has already passed above the visible area.
        for _ in 0..<12 where !element.isHittable {
            let area = scroller ?? app
            let moveDown = element.exists && element.frame.maxY < area.frame.midY
            let start = area.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: moveDown ? 0.4 : 0.7))
            let end = area.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: moveDown ? 0.65 : 0.45))
            start.press(forDuration: 0.05, thenDragTo: end)
        }
    }
    func testScreens() throws {
        let app = XCUIApplication()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        for tab in ["Recap", "People", "Chat", "Places", "Pins"] {
            app.thoughtPinsTab(tab).tap()
            shot(tab, app)
        }
        app.thoughtPinsTab("Recap").tap()
        let rating = app.buttons["Importance rating"].firstMatch
        reveal(rating, in: app)
        rating.tap()
        app.buttons["Set importance to 3 out of 5"].tap()
        let rated = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "3 out of 5"), object: rating)
        XCTAssertEqual(XCTWaiter.wait(for: [rated], timeout: 5), .completed)
        app.thoughtPinsTab("People").tap()
        let search = app.textFields["Search people"]
        search.tap()
        search.typeText("nomatchingperson\n")
        XCTAssertTrue(app.staticTexts["No matches"].waitForExistence(timeout: 5))
        app.buttons["Clear search"].tap()
        app.thoughtPinsTab("Chat").tap()
        let prompt = app.buttons["What has been on my mind?"]
        if !prompt.isHittable { app.swipeDown() }
        prompt.tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "I remember the Atlas")).firstMatch.waitForExistence(timeout: 10))
        shot("Chat-reply", app)
        app.buttons["Account"].firstMatch.tap()
        XCTAssertTrue(app.buttons["Export account"].waitForExistence(timeout: 5))
        shot("Account", app)
        app.swipeUp()
        app.swipeUp()
        app.buttons["Sign out"].tap()
        XCTAssertTrue(app.secureTextFields["Password"].waitForExistence(timeout: 5))
        shot("Auth", app)
        app.buttons["Create account"].firstMatch.tap()
        XCTAssertTrue(app.switches.firstMatch.exists)
        app.buttons["Sign in"].firstMatch.tap()
        let email = app.textFields["Email"]
        email.tap()
        // Next uses the form's focus/scroll contract. Tapping an offscreen
        // password field through the keyboard fails AX scrolling on iPhone SE.
        email.typeText("review@example.com\n")
        let password = app.secureTextFields["Password"]
        let keyboardReady = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "hittable == true"), object: app.keyboards.keys["a"]
        )
        XCTAssertEqual(XCTWaiter.wait(for: [keyboardReady], timeout: 20), .completed)
        let focused = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in
                password.exists && password.frame.minY.isFinite && password.isHittable
            }, object: password
        )
        XCTAssertEqual(XCTWaiter.wait(for: [focused], timeout: 5), .completed)
        password.typeText("fictional password only\n")
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 10))
    }

    func testChatComposer() throws {
        let app = XCUIApplication()
        app.launchArguments = []
        app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any)["thoughtpins-chat-input"]
        composer.tap()
        composer.typeText("What should I remember?")
        app.buttons["thoughtpins-chat-send"].tap()
        let reply = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "I remember the Atlas")).firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        shot("Chat-reply", app)
    }

    // The disposable host sets Dynamic Type to accessibility5 for this launch.
    // Check the actual control, not just its presence in the view tree.
    func testAccessibilityScreens() throws {
        let app = XCUIApplication()
        app.launchArguments += ["--accessibility-review"]
        app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any)["thoughtpins-chat-input"]
        XCTAssertTrue(composer.isHittable)
        XCTAssertTrue(app.buttons["thoughtpins-chat-send"].exists)
        shot("Chat", app)
        composer.tap()
        composer.typeText("What should I remember?")
        app.buttons["thoughtpins-chat-send"].tap()
        let reply = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "I remember the Atlas")).firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        reveal(reply, in: app, scroller: app.scrollViews.firstMatch)
        XCTAssertTrue(reply.isHittable)
        shot("Chat-reply", app)
        for tab in ["Recap", "People", "Places", "Pins"] {
            app.thoughtPinsTab(tab).tap()
            shot(tab, app)
            if tab != "Recap" {
                let search = app.textFields["Search \(tab.lowercased())"]
                reveal(search, in: app)
                XCTAssertTrue(search.isHittable)
                search.tap()
                search.typeText("no matching content\n")
                XCTAssertTrue(app.staticTexts["No matches"].waitForExistence(timeout: 5))
                app.buttons["Clear search"].tap()
            }
        }
    }

    func testLandscapeScreens() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.thoughtPinsTab("Chat").waitForExistence(timeout: 20))
        guard app.frame.width >= 700 else {
            throw XCTSkip("The production iPhone target supports portrait; rotation is reviewed on iPad.")
        }
        XCUIDevice.shared.orientation = .landscapeLeft
        defer { XCUIDevice.shared.orientation = .portrait }
        let landscape = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in app.frame.width > app.frame.height }, object: app)
        XCTAssertEqual(XCTWaiter.wait(for: [landscape], timeout: 5), .completed)
        XCTAssertTrue(app.descendants(matching: .any)["thoughtpins-chat-input"].isHittable)
        for tab in ["Chat", "Recap", "People", "Places", "Pins"] {
            app.thoughtPinsTab(tab).tap()
            shot(tab, app)
        }
    }
}
