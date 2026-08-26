import Foundation
import SwiftUI
import ThoughtPinsCore

// Rendering a model reply: block structure first, then inline Markdown per
// block. Split out of ThoughtPinsScreens.swift when that file reached its size
// budget. The parser itself lives in ThoughtPinsCore so it can be tested
// without a view.

/// Resolve the inline Markdown of **one already marker-free line**.
///
/// `.inlineOnlyPreservingWhitespace` resolves bold, italic, inline code and
/// links, and leaves every *block* marker sitting in the text — so this must
/// only ever be handed the content of a block, after
/// `thoughtPinsParseReplyBlocks` has removed the marker. Handing it a whole
/// multi-block reply is what printed `>` and `- ` on screen.
///
/// Never hand it the contents of a code block: this mode reads a ``` fence as
/// an inline code span, which drops the newlines inside it.
///
/// The `try?` is defensive only. cmark does not reject malformed Markdown — an
/// unterminated `**`, a stray `[`, a lone backtick are all parsed as literal
/// text — so the fallback is not expected to fire.
func thoughtPinsFormattedReply(_ raw: String) -> AttributedString {
    (try? AttributedString(
        markdown: raw,
        options: AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
    )) ?? AttributedString(raw)
}

/// A model reply, rendered block by block.
///
/// See `ThoughtPinsReplyBlock` for why block structure is decided before any
/// Markdown parser sees the text.
struct ThoughtPinsReplyView: View {
    let reply: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(thoughtPinsParseReplyBlocks(reply).enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let text):
                    Text(thoughtPinsFormattedReply(text))
                        .font(.body)
                case .heading(let level, let text):
                    Text(thoughtPinsFormattedReply(text))
                        .font(.system(level <= 2 ? .headline : .subheadline, design: .serif).weight(.semibold))
                        .padding(.top, 2)
                case .bullet(let text, let depth):
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\u{2022}").font(.body)
                        Text(thoughtPinsFormattedReply(text)).font(.body)
                    }
                    .padding(.leading, CGFloat(depth) * 14)
                case .numbered(let number, let text, let depth):
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\(number).").font(.body.monospacedDigit())
                        Text(thoughtPinsFormattedReply(text)).font(.body)
                    }
                    .padding(.leading, CGFloat(depth) * 14)
                case .quote(let text):
                    HStack(alignment: .top, spacing: 8) {
                        Rectangle()
                            .fill(ThoughtPinsTheme.brand)
                            .frame(width: 3)
                        Text(thoughtPinsFormattedReply(text))
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                case .code(let code):
                    // Verbatim: never through the Markdown parser, so backticks
                    // and asterisks inside code survive as typed.
                    ScrollView(.horizontal, showsIndicators: false) {
                        Text(code)
                            .font(.system(.callout, design: .monospaced))
                            .padding(8)
                    }
                    .background(ThoughtPinsTheme.brandSoft, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                case .rule:
                    Divider()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
