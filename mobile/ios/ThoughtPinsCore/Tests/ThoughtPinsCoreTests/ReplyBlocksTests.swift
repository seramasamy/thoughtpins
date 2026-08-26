import Foundation
import XCTest
@testable import ThoughtPinsCore

/// Acceptance for P1.3: a reply using every block construct must render with no
/// stray syntax characters.
final class ThoughtPinsReplyBlocksTests: XCTestCase {
    /// Every marker character that must never survive into displayed text.
    private func assertNoStraySyntax(_ blocks: [ThoughtPinsReplyBlock], file: StaticString = #filePath, line: UInt = #line) {
        for block in blocks {
            switch block {
            case .code:
                continue  // code is verbatim on purpose
            case .rule:
                continue
            case .paragraph(let text), .quote(let text),
                 .heading(_, let text), .bullet(let text, _), .numbered(_, let text, _):
                for marker in ["```", "~~~"] {
                    XCTAssertFalse(text.contains(marker), "\(marker) leaked into \(text)", file: file, line: line)
                }
                XCTAssertFalse(text.hasPrefix(">"), "quote marker leaked into \(text)", file: file, line: line)
                XCTAssertFalse(text.hasPrefix("#"), "heading marker leaked into \(text)", file: file, line: line)
                XCTAssertFalse(text.hasPrefix("- "), "bullet marker leaked into \(text)", file: file, line: line)
                XCTAssertFalse(text.hasPrefix("* "), "bullet marker leaked into \(text)", file: file, line: line)
                XCTAssertFalse(text.hasPrefix("+ "), "bullet marker leaked into \(text)", file: file, line: line)
            }
        }
    }

    func testAReplyUsingEveryBlockConstructLeavesNoStraySyntax() {
        let reply = """
        # What I remember

        According to your journal:

        > You met Maya at Atlas Cafe.
        > She noticed the copper lantern.

        - a bullet
        * another bullet
        + a third bullet

        1. first
        2) second

        ## A smaller heading

        ```swift
        let x = 1
        let y = 2
        ```

        ---

        That is everything.
        """
        let blocks = thoughtPinsParseReplyBlocks(reply)
        assertNoStraySyntax(blocks)

        XCTAssertTrue(blocks.contains(.heading(level: 1, text: "What I remember")))
        XCTAssertTrue(blocks.contains(.heading(level: 2, text: "A smaller heading")))
        XCTAssertTrue(blocks.contains(.quote("You met Maya at Atlas Cafe. She noticed the copper lantern.")))
        XCTAssertTrue(blocks.contains(.bullet(text: "a bullet", depth: 0)))
        XCTAssertTrue(blocks.contains(.bullet(text: "another bullet", depth: 0)))
        XCTAssertTrue(blocks.contains(.bullet(text: "a third bullet", depth: 0)))
        XCTAssertTrue(blocks.contains(.numbered(number: 1, text: "first", depth: 0)))
        XCTAssertTrue(blocks.contains(.numbered(number: 2, text: "second", depth: 0)))
        XCTAssertTrue(blocks.contains(.rule))
        XCTAssertTrue(blocks.contains(.paragraph("That is everything.")))
    }

    /// The data-corruption case: a fence must keep its newlines and must not
    /// promote its info string to visible text.
    func testCodeFencesKeepTheirLinesAndDropTheInfoString() {
        let blocks = thoughtPinsParseReplyBlocks("```swift\nlet x = 1\nlet y = 2\n```")
        XCTAssertEqual(blocks, [.code("let x = 1\nlet y = 2")])

        guard case .code(let code)? = blocks.first else { return XCTFail("not a code block") }
        XCTAssertTrue(code.contains("\n"), "the newline between the two lines was lost")
        XCTAssertFalse(code.contains("swift"), "the fence info string became content")
    }

    func testMarkersInsideCodeSurviveAsTyped() {
        let blocks = thoughtPinsParseReplyBlocks("```\n- not a bullet\n# not a heading\n**not bold**\n```")
        XCTAssertEqual(blocks, [.code("- not a bullet\n# not a heading\n**not bold**")])
    }

    func testRulesAreNotMistakenForBullets() {
        XCTAssertEqual(thoughtPinsParseReplyBlocks("---"), [.rule])
        XCTAssertEqual(thoughtPinsParseReplyBlocks("***"), [.rule])
        XCTAssertEqual(thoughtPinsParseReplyBlocks("___"), [.rule])
        // A dash with text is a bullet, not a rule.
        XCTAssertEqual(thoughtPinsParseReplyBlocks("- item"), [.bullet(text: "item", depth: 0)])
    }

    func testConsecutiveParagraphLinesBecomeOneParagraph() {
        let blocks = thoughtPinsParseReplyBlocks("one line\nand its continuation\n\na second paragraph")
        XCTAssertEqual(blocks, [
            .paragraph("one line and its continuation"),
            .paragraph("a second paragraph"),
        ])
    }

    func testNestingDepthIsKept() {
        let blocks = thoughtPinsParseReplyBlocks("- outer\n  - inner\n    - deeper")
        XCTAssertEqual(blocks, [
            .bullet(text: "outer", depth: 0),
            .bullet(text: "inner", depth: 1),
            .bullet(text: "deeper", depth: 2),
        ])
    }

    func testNestedQuotesCollapseWithoutLeakingMarkers() {
        let blocks = thoughtPinsParseReplyBlocks("> outer\n>> inner")
        XCTAssertEqual(blocks, [.quote("outer inner")])
        assertNoStraySyntax(blocks)
    }

    func testAnUnterminatedFenceStillShowsAsCodeRatherThanBackticks() {
        let blocks = thoughtPinsParseReplyBlocks("```\nlet x = 1")
        XCTAssertEqual(blocks, [.code("let x = 1")])
    }

    /// Inline syntax is deliberately left alone: the view resolves it.
    func testInlineSyntaxIsLeftForTheInlineParser() {
        let blocks = thoughtPinsParseReplyBlocks("- **bold** and `code` and [a](b)")
        XCTAssertEqual(blocks, [.bullet(text: "**bold** and `code` and [a](b)", depth: 0)])
    }

    func testAnOrdinaryReplyIsUnchanged() {
        let blocks = thoughtPinsParseReplyBlocks("According to your journal, you met Maya today.")
        XCTAssertEqual(blocks, [.paragraph("According to your journal, you met Maya today.")])
    }

    func testEmptyRepliesProduceNothing() {
        XCTAssertEqual(thoughtPinsParseReplyBlocks(""), [])
        XCTAssertEqual(thoughtPinsParseReplyBlocks("\n\n  \n"), [])
    }
}
