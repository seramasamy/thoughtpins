import SwiftUI
import UIKit

private let thoughtPinsTerracotta = Color(red: 0.9098, green: 0.3804, blue: 0.1686)

public struct ThoughtPinsBrandMark: View {
    public init() {}

    public var body: some View {
        GeometryReader { geometry in
            let dimension = min(geometry.size.width, geometry.size.height)
            ZStack {
                RoundedRectangle(cornerRadius: dimension * 28 / 128, style: .continuous)
                    .fill(thoughtPinsTerracotta)
                MemoryPinSilhouette()
                    .fill(.white)
                MemoryPinGrooves()
                    .stroke(
                        thoughtPinsTerracotta,
                        style: StrokeStyle(
                            lineWidth: dimension * 5.5 / 128,
                            lineCap: .round,
                            lineJoin: .round
                        )
                    )
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityHidden(true)
    }
}

private struct MemoryPinSilhouette: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let scale = min(rect.width, rect.height) / 128
        let origin = CGPoint(
            x: rect.midX - 64 * scale,
            y: rect.midY - 64 * scale
        )
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: origin.x + x * scale, y: origin.y + y * scale)
        }
        path.move(to: point(64, 17))
        path.addCurve(to: point(22, 57.5), control1: point(39.7, 17), control2: point(22, 34.4))
        path.addCurve(to: point(64, 121), control1: point(22, 78.3), control2: point(37.7, 94.9))
        path.addCurve(to: point(106, 57.5), control1: point(90.3, 94.9), control2: point(106, 78.3))
        path.addCurve(to: point(64, 17), control1: point(106, 34.4), control2: point(88.3, 17))
        path.closeSubpath()
        return path.applying(CGAffineTransform(a: 0.94, b: 0, c: 0, d: 0.94, tx: 3.84 * scale, ty: -1.16 * scale))
    }
}

private struct MemoryPinGrooves: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let scale = min(rect.width, rect.height) / 128
        let origin = CGPoint(
            x: rect.midX - 64 * scale,
            y: rect.midY - 64 * scale
        )
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: origin.x + x * scale, y: origin.y + y * scale)
        }
        path.move(to: point(64, 29))
        path.addLine(to: point(64, 93))

        path.move(to: point(53, 29))
        path.addCurve(to: point(40, 38), control1: point(45, 26), control2: point(40, 31))
        path.addCurve(to: point(50, 48), control1: point(40, 44), control2: point(44, 47))
        path.move(to: point(39, 41))
        path.addCurve(to: point(35, 60), control1: point(32, 45), control2: point(31, 54))
        path.addCurve(to: point(50, 62), control1: point(39, 65), control2: point(44, 65))
        path.move(to: point(35, 63))
        path.addCurve(to: point(45, 82), control1: point(33, 72), control2: point(37, 80))
        path.addCurve(to: point(55, 93), control1: point(52, 84), control2: point(55, 88))

        path.move(to: point(75, 29))
        path.addCurve(to: point(88, 38), control1: point(83, 26), control2: point(88, 31))
        path.addCurve(to: point(78, 48), control1: point(88, 44), control2: point(84, 47))
        path.move(to: point(89, 41))
        path.addCurve(to: point(93, 60), control1: point(96, 45), control2: point(97, 54))
        path.addCurve(to: point(78, 62), control1: point(89, 65), control2: point(84, 65))
        path.move(to: point(93, 63))
        path.addCurve(to: point(83, 82), control1: point(95, 72), control2: point(91, 80))
        path.addCurve(to: point(73, 93), control1: point(76, 84), control2: point(73, 88))
        return path.applying(CGAffineTransform(a: 0.94, b: 0, c: 0, d: 0.94, tx: 3.84 * scale, ty: -1.16 * scale))
    }
}
