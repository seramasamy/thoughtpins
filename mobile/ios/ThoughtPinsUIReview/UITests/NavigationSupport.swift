import XCTest

extension XCUIApplication {
    func thoughtPinsTab(_ name: String) -> XCUIElement {
        // iPadOS 18+ exposes floating tab items as cells outside a TabBar.
        // Match the interactive item, excluding the screen's text heading.
        descendants(matching: .any).matching(NSPredicate(
            format: "label == %@ AND (elementType == %d OR elementType == %d)",
            name, XCUIElement.ElementType.button.rawValue, XCUIElement.ElementType.cell.rawValue
        )).firstMatch
    }
}
