import SwiftUI

/// A static, resolution-independent network for welcome and empty states.
/// Its footprint stays consistent from compact sign-in to the iPad canvas.
struct ThoughtPinsOrbit: View {
    var size: CGFloat = 132
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let points: [CGPoint] = [
        CGPoint(x: 0.17, y: 0.23), CGPoint(x: 0.69, y: 0.12),
        CGPoint(x: 0.92, y: 0.44), CGPoint(x: 0.76, y: 0.82),
        CGPoint(x: 0.28, y: 0.89), CGPoint(x: 0.08, y: 0.59)
    ]

    var body: some View {
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [ThoughtPinsTheme.accentSoft, ThoughtPinsTheme.canvas],
                                     center: .center, startRadius: 0, endRadius: size * 0.5))
                .padding(size * 0.04)
            Circle()
                .stroke(ThoughtPinsTheme.line, style: StrokeStyle(lineWidth: 0.8, dash: [2, 5]))
                .padding(size * 0.05)
            Path { path in
                let scaled = points.map { CGPoint(x: $0.x * size, y: $0.y * size) }
                for index in scaled.indices {
                    path.move(to: scaled[index])
                    path.addLine(to: scaled[(index + 1) % scaled.count])
                    if index.isMultiple(of: 2) {
                        path.move(to: scaled[index])
                        path.addLine(to: CGPoint(x: size * 0.5, y: size * 0.5))
                    }
                }
            }
            .stroke(LinearGradient(colors: [ThoughtPinsTheme.accent.opacity(0.55), ThoughtPinsTheme.line],
                                   startPoint: .topTrailing, endPoint: .bottomLeading), lineWidth: 0.8)
            Circle().fill(ThoughtPinsTheme.surface).frame(width: size * 0.59, height: size * 0.59)
                .overlay(Circle().stroke(ThoughtPinsTheme.line, lineWidth: 0.8))
            ThoughtPinsBrandMark().frame(width: size * 0.41, height: size * 0.41)
                .shadow(color: reduceTransparency ? .clear : ThoughtPinsTheme.brand.opacity(0.12),
                        radius: size * 0.06, y: size * 0.025)
            ForEach(points.indices, id: \.self) { index in
                Circle().fill(index == 1 ? ThoughtPinsTheme.brand : ThoughtPinsTheme.accent)
                    .frame(width: max(3, size * 0.035), height: max(3, size * 0.035))
                    .overlay(Circle().stroke(ThoughtPinsTheme.canvas, lineWidth: 1))
                    .position(x: points[index].x * size, y: points[index].y * size)
            }
        }
        .frame(width: size, height: size)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
