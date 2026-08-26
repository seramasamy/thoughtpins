import Foundation

/// One block of a model reply, with its Markdown marker already removed.
///
/// Replies arrive as Markdown. `AttributedString(markdown:)` in
/// `.inlineOnlyPreservingWhitespace` resolves bold, italic, inline code and
/// links, and leaves every *block* marker in the text — so `> quoted`,
/// `- item`, `# Heading` and `1. first` were all printed with their markers
/// visible. Worse, a ``` fence is misread as an inline code span: the info
/// string becomes visible content and the newlines inside the block are lost,
/// so `\`\`\`swift\nlet x = 1\nlet y = 2\n\`\`\`` rendered as
/// `swift let x = 1 let y = 2` — the code shown wrong, not merely ugly.
///
/// So block structure is decided here, before any Markdown parser sees the
/// text, and the view applies inline parsing to the marker-free content of each
/// block. Code blocks are never passed to the Markdown parser at all, so
/// backticks, asterisks and underscores inside code survive as typed.
public enum ThoughtPinsReplyBlock: Equatable, Sendable {
    case paragraph(String)
    case heading(level: Int, text: String)
    case bullet(text: String, depth: Int)
    case numbered(number: Int, text: String, depth: Int)
    case quote(String)
    case code(String)
    case rule
}

/// Split a reply into blocks, stripping every block-level Markdown marker.
public func thoughtPinsParseReplyBlocks(_ raw: String) -> [ThoughtPinsReplyBlock] {
    var blocks: [ThoughtPinsReplyBlock] = []
    var paragraph: [String] = []
    var quote: [String] = []
    var code: [String] = []
    var inFence = false

    func flushParagraph() {
        guard !paragraph.isEmpty else { return }
        blocks.append(.paragraph(paragraph.joined(separator: " ")))
        paragraph = []
    }
    func flushQuote() {
        guard !quote.isEmpty else { return }
        blocks.append(.quote(quote.joined(separator: " ")))
        quote = []
    }
    func flushText() {
        flushParagraph()
        flushQuote()
    }

    for line in raw.components(separatedBy: .newlines) {
        let trimmed = line.trimmingCharacters(in: .whitespaces)

        // Fences first: everything between them is verbatim, including things
        // that would otherwise look like markers.
        if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
            if inFence {
                blocks.append(.code(code.joined(separator: "\n")))
                code = []
                inFence = false
            } else {
                flushText()
                inFence = true
            }
            continue
        }
        if inFence {
            code.append(line)
            continue
        }

        if trimmed.isEmpty {
            flushText()
            continue
        }

        // Rules before bullets, or `---` and `***` become list items.
        if isThoughtPinsRule(trimmed) {
            flushText()
            blocks.append(.rule)
            continue
        }

        let depth = thoughtPinsIndentDepth(line)

        if let heading = thoughtPinsHeading(trimmed) {
            flushText()
            blocks.append(.heading(level: heading.level, text: heading.text))
            continue
        }
        if let text = thoughtPinsBullet(trimmed) {
            flushText()
            blocks.append(.bullet(text: text, depth: depth))
            continue
        }
        if let item = thoughtPinsNumbered(trimmed) {
            flushText()
            blocks.append(.numbered(number: item.number, text: item.text, depth: depth))
            continue
        }
        if let text = thoughtPinsQuote(trimmed) {
            flushParagraph()
            quote.append(text)
            continue
        }

        flushQuote()
        paragraph.append(trimmed)
    }

    if inFence, !code.isEmpty {
        // An unterminated fence still has to show its contents as code rather
        // than leaking backticks.
        blocks.append(.code(code.joined(separator: "\n")))
    }
    flushText()
    return blocks
}

private func isThoughtPinsRule(_ trimmed: String) -> Bool {
    let stripped = trimmed.replacingOccurrences(of: " ", with: "")
    guard stripped.count >= 3, let first = stripped.first, "-*_".contains(first) else { return false }
    return stripped.allSatisfy { $0 == first }
}

private func thoughtPinsIndentDepth(_ line: String) -> Int {
    var spaces = 0
    for character in line {
        if character == " " { spaces += 1 } else if character == "\t" { spaces += 4 } else { break }
    }
    return spaces / 2
}

private func thoughtPinsHeading(_ trimmed: String) -> (level: Int, text: String)? {
    var level = 0
    var rest = Substring(trimmed)
    while rest.first == "#", level < 6 {
        level += 1
        rest = rest.dropFirst()
    }
    guard level > 0, rest.first == " " else { return nil }
    let text = rest.trimmingCharacters(in: .whitespaces)
    return text.isEmpty ? nil : (level, text)
}

private func thoughtPinsBullet(_ trimmed: String) -> String? {
    guard let marker = trimmed.first, "-*+".contains(marker) else { return nil }
    let rest = trimmed.dropFirst()
    guard rest.first == " " else { return nil }
    let text = rest.trimmingCharacters(in: .whitespaces)
    return text.isEmpty ? nil : text
}

private func thoughtPinsNumbered(_ trimmed: String) -> (number: Int, text: String)? {
    var digits = ""
    var rest = Substring(trimmed)
    while let first = rest.first, first.isNumber, digits.count < 9 {
        digits.append(first)
        rest = rest.dropFirst()
    }
    guard !digits.isEmpty, let number = Int(digits) else { return nil }
    guard let separator = rest.first, separator == "." || separator == ")" else { return nil }
    rest = rest.dropFirst()
    guard rest.first == " " else { return nil }
    let text = rest.trimmingCharacters(in: .whitespaces)
    return text.isEmpty ? nil : (number, text)
}

private func thoughtPinsQuote(_ trimmed: String) -> String? {
    guard trimmed.hasPrefix(">") else { return nil }
    var rest = Substring(trimmed)
    // Nested quotes collapse to one level; the app renders a single rule.
    while rest.first == ">" {
        rest = rest.dropFirst()
        if rest.first == " " { rest = rest.dropFirst() }
    }
    return String(rest)
}
