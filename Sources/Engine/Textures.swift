import UIKit

/// All textures in the game are generated procedurally with CoreGraphics —
/// no image assets are shipped with the app.
enum Textures {

    static func image(_ size: CGFloat, _ draw: (CGContext, CGFloat) -> Void) -> UIImage {
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: size, height: size))
        return renderer.image { ctx in draw(ctx.cgContext, size) }
    }

    /// Granite cobblestones of Palace Square, dusted with snow.
    static let cobblestone: UIImage = {
        return image(512) { ctx, s in
            var rnd = SeededRandom(seed: 7)
            ctx.setFillColor(UIColor(red: 0.30, green: 0.31, blue: 0.34, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            let cell: CGFloat = 32
            var row = 0
            var y: CGFloat = 0
            while y < s {
                var x: CGFloat = (row % 2 == 0) ? 0 : -cell / 2
                while x < s + cell {
                    let g = CGFloat(rnd.range(0.32, 0.48))
                    ctx.setFillColor(UIColor(red: g, green: g, blue: g + 0.03, alpha: 1).cgColor)
                    let rect = CGRect(x: x + 2.5, y: y + 2.5, width: cell - 5, height: cell - 5)
                    let path = UIBezierPath(roundedRect: rect, cornerRadius: 6)
                    ctx.addPath(path.cgPath)
                    ctx.fillPath()
                    if rnd.next() < 0.4 {
                        let w = CGFloat(rnd.range(6, 20))
                        ctx.setFillColor(UIColor(white: 0.93, alpha: CGFloat(rnd.range(0.25, 0.65))).cgColor)
                        ctx.fillEllipse(in: CGRect(x: x + CGFloat(rnd.range(3, 16)),
                                                   y: y + CGFloat(rnd.range(3, 16)),
                                                   width: w, height: w * 0.55))
                    }
                    x += cell
                }
                y += cell
                row += 1
            }
        }
    }()

    /// Bare summer cobblestones — the same masonry without snow dust.
    static let cobblestoneSummer: UIImage = {
        return image(512) { ctx, s in
            var rnd = SeededRandom(seed: 7)
            ctx.setFillColor(UIColor(red: 0.27, green: 0.27, blue: 0.29, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            let cell: CGFloat = 32
            var row = 0
            var y: CGFloat = 0
            while y < s {
                var x: CGFloat = (row % 2 == 0) ? 0 : -cell / 2
                while x < s + cell {
                    let g = CGFloat(rnd.range(0.30, 0.46))
                    ctx.setFillColor(UIColor(red: g, green: g * 0.98, blue: g * 0.94, alpha: 1).cgColor)
                    let rect = CGRect(x: x + 2.5, y: y + 2.5, width: cell - 5, height: cell - 5)
                    let path = UIBezierPath(roundedRect: rect, cornerRadius: 6)
                    ctx.addPath(path.cgPath)
                    ctx.fillPath()
                    _ = rnd.next() // keep the sequence aligned with the winter texture
                    x += cell
                }
                y += cell
                row += 1
            }
        }
    }()

    /// Winter Palace facade. In the 1890s the palace was painted in the
    /// dark terracotta-red of the era (the familiar green came only in the
    /// Soviet period).
    static let palaceWall: UIImage = {
        return image(256) { ctx, s in
            var rnd = SeededRandom(seed: 21)
            ctx.setFillColor(UIColor(red: 0.55, green: 0.25, blue: 0.20, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            for _ in 0..<400 {
                let a = CGFloat(rnd.range(0.03, 0.10))
                let bright = rnd.next() < 0.5
                ctx.setFillColor(UIColor(white: bright ? 0.9 : 0.05, alpha: a).cgColor)
                let w = CGFloat(rnd.range(4, 26))
                ctx.fillEllipse(in: CGRect(x: CGFloat(rnd.range(0, 256)),
                                           y: CGFloat(rnd.range(0, 256)),
                                           width: w, height: w * 0.4))
            }
            // faint rustication lines
            ctx.setStrokeColor(UIColor(white: 0.1, alpha: 0.12).cgColor)
            ctx.setLineWidth(2)
            var y: CGFloat = 32
            while y < s {
                ctx.move(to: CGPoint(x: 0, y: y))
                ctx.addLine(to: CGPoint(x: s, y: y))
                y += 32
            }
            ctx.strokePath()
        }
    }()

    /// The yellow-and-white walls of the General Staff Building.
    static let staffWall: UIImage = {
        return image(256) { ctx, s in
            var rnd = SeededRandom(seed: 33)
            ctx.setFillColor(UIColor(red: 0.78, green: 0.63, blue: 0.32, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            for _ in 0..<300 {
                let a = CGFloat(rnd.range(0.03, 0.09))
                let bright = rnd.next() < 0.5
                ctx.setFillColor(UIColor(white: bright ? 0.95 : 0.1, alpha: a).cgColor)
                let w = CGFloat(rnd.range(4, 22))
                ctx.fillEllipse(in: CGRect(x: CGFloat(rnd.range(0, 256)),
                                           y: CGFloat(rnd.range(0, 256)),
                                           width: w, height: w * 0.4))
            }
        }
    }()

    /// A tall 19th-century window with white frames.
    static let windowGlass: UIImage = {
        return image(128) { ctx, s in
            ctx.setFillColor(UIColor(red: 0.08, green: 0.12, blue: 0.18, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            // warm candle glow in some panes
            ctx.setFillColor(UIColor(red: 0.85, green: 0.65, blue: 0.3, alpha: 0.35).cgColor)
            ctx.fill(CGRect(x: 12, y: 12, width: s / 2 - 16, height: s / 2 - 16))
            ctx.setStrokeColor(UIColor(white: 0.92, alpha: 1).cgColor)
            ctx.setLineWidth(10)
            ctx.stroke(CGRect(x: 5, y: 5, width: s - 10, height: s - 10))
            ctx.setLineWidth(6)
            ctx.move(to: CGPoint(x: s / 2, y: 0))
            ctx.addLine(to: CGPoint(x: s / 2, y: s))
            ctx.move(to: CGPoint(x: 0, y: s / 2))
            ctx.addLine(to: CGPoint(x: s, y: s / 2))
            ctx.strokePath()
        }
    }()

    /// Red Finnish granite of the Alexander Column.
    static let granite: UIImage = {
        return image(256) { ctx, s in
            var rnd = SeededRandom(seed: 55)
            ctx.setFillColor(UIColor(red: 0.45, green: 0.28, blue: 0.24, alpha: 1).cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            for _ in 0..<900 {
                let a = CGFloat(rnd.range(0.05, 0.2))
                let bright = rnd.next() < 0.45
                ctx.setFillColor(UIColor(white: bright ? 0.85 : 0.1, alpha: a).cgColor)
                let w = CGFloat(rnd.range(1.5, 6))
                ctx.fillEllipse(in: CGRect(x: CGFloat(rnd.range(0, 256)),
                                           y: CGFloat(rnd.range(0, 256)),
                                           width: w, height: w))
            }
        }
    }()

    /// Soft round particle used for falling snow.
    static let snowflake: UIImage = {
        return image(64) { ctx, s in
            let colors = [UIColor(white: 1, alpha: 1).cgColor,
                          UIColor(white: 1, alpha: 0).cgColor] as CFArray
            let space = CGColorSpaceCreateDeviceRGB()
            if let gradient = CGGradient(colorsSpace: space, colors: colors, locations: [0, 1]) {
                let c = CGPoint(x: s / 2, y: s / 2)
                ctx.drawRadialGradient(gradient, startCenter: c, startRadius: 0,
                                       endCenter: c, endRadius: s / 2, options: [])
            }
        }
    }()
}
