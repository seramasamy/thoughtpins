import XCTest

final class RecoveryTests: XCTestCase {
    private func configure(_ failures: [String: [Int]] = [:]) throws {
        let done = expectation(description: "Configure fictional local API")
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8877/__review")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["failures": failures])
        URLSession.shared.dataTask(with: request) { _, response, error in
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            done.fulfill()
        }.resume()
        wait(for: [done], timeout: 5)
    }

    override func tearDownWithError() throws { try configure() }

    func testFailedChatKeepsDraftAndRetryKeepsTheQuestion() throws {
        try configure(["POST /v1/chat": [503, 429]])
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any)["thoughtpins-chat-input"]
        let send = app.buttons["thoughtpins-chat-send"]
        composer.tap()
        composer.typeText("A fictional detail to keep safe.")
        for _ in 0..<2 {
            send.tap()
            let restored = XCTNSPredicateExpectation(
                predicate: NSPredicate(format: "value == %@", "A fictional detail to keep safe."), object: composer
            )
            XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 10), .completed)
            XCTAssertTrue(send.isEnabled)
        }
        send.tap()
        let reply = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "I remember the Atlas")).firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["A fictional detail to keep safe."].exists)
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        screenshot.name = "Recovered-chat"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testWhitespaceCannotSubmitAndSearchRecovers() throws {
        try configure()
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any)["thoughtpins-chat-input"]
        composer.tap()
        composer.typeText("   ")
        XCTAssertFalse(app.buttons["thoughtpins-chat-send"].isEnabled)
        app.buttons["Dismiss keyboard"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        app.tabBars.buttons["People"].tap()
        let search = app.textFields["Search people"]
        search.tap()
        search.typeText("a fictional missing name\n")
        XCTAssertTrue(app.staticTexts["No matches"].waitForExistence(timeout: 5))
        app.buttons["Clear search"].tap()
        XCTAssertFalse(app.staticTexts["No matches"].exists)
        XCTAssertFalse(app.keyboards.firstMatch.exists)
    }

    func testExportProducesAShareSheetAndDeletionCanBeCancelled() throws {
        try configure()
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 20))
        app.buttons["Account"].firstMatch.tap()
        let export = app.buttons["Export account"]
        XCTAssertTrue(export.waitForExistence(timeout: 5))
        export.tap()
        // Activity rows are cells on iOS 17, rather than XCUI buttons.
        let saveToFiles = app.descendants(matching: .any).matching(
            NSPredicate(format: "label == %@", "Save to Files")
        ).firstMatch
        XCTAssertTrue(saveToFiles.waitForExistence(timeout: 10))
        let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        screenshot.name = "Account-export"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        app.buttons["Close"].tap()
        let remove = app.buttons["Delete account"]
        for _ in 0..<5 where !remove.isHittable { app.swipeUp() }
        remove.tap()
        XCTAssertTrue(app.buttons["Cancel"].waitForExistence(timeout: 5))
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.navigationBars["Account"].exists)
    }

    func testVoiceDisclosureCanBeCancelledWithoutRecording() throws {
        try configure()
        let app = XCUIApplication()
        app.launchArguments = ["-thoughtpins.voiceDisclosure.2026-07-13", "NO"]
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Chat"].waitForExistence(timeout: 20))
        app.buttons["Record a voice note"].tap()
        XCTAssertTrue(app.alerts["Record a voice note"].waitForExistence(timeout: 5))
        app.alerts.buttons["Cancel"].tap()
        XCTAssertFalse(app.staticTexts["Recording voice note"].exists)
        XCTAssertTrue(app.buttons["Record a voice note"].isEnabled)
    }
}
