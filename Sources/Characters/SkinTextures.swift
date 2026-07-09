import UIKit

/// Procedural textures for the realistic character pipeline: skin with lips
/// and blush painted in the head's UV space, streaky hair, and woven cloth.
enum SkinTextures {

    private static var faceCache: [String: UIImage] = [:]
    private static var hairCache: [String: UIImage] = [:]
    private static var clothCache: [String: UIImage] = [:]

    private static func key(_ c: UIColor) -> String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        c.getRed(&r, green: &g, blue: &b, alpha: &a)
        return "\(Int(r * 255))-\(Int(g * 255))-\(Int(b * 255))"
    }

    /// Head texture. UV layout comes from FaceBuilder's parametric shell:
    /// u = (phi + pi) / 2pi  (0.5 is the face center), v = theta / pi.
    static func face(tone: UIColor) -> UIImage {
        let k = key(tone)
        if let cached = faceCache[k] { return cached }

        let img = Textures.image(512) { ctx, s in
            var rnd = SeededRandom(seed: 404)
            ctx.setFillColor(tone.cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))

            // gentle skin mottling
            var tr: CGFloat = 0, tg: CGFloat = 0, tb: CGFloat = 0, ta: CGFloat = 0
            tone.getRed(&tr, green: &tg, blue: &tb, alpha: &ta)
            for _ in 0..<600 {
                let dv = CGFloat(rnd.range(-0.045, 0.045))
                ctx.setFillColor(UIColor(red: min(1, tr + dv), green: min(1, tg + dv * 0.9),
                                         blue: min(1, tb + dv * 0.8), alpha: 0.35).cgColor)
                let w = CGFloat(rnd.range(3, 14))
                ctx.fillEllipse(in: CGRect(x: CGFloat(rnd.range(0, 512)), y: CGFloat(rnd.range(0, 512)),
                                           width: w, height: w * 0.7))
            }

            // v coordinates of face landmarks (theta / pi * 512)
            let vMouth: CGFloat = 2.24 / CGFloat.pi * s
            let vCheek: CGFloat = 1.85 / CGFloat.pi * s
            let uCenter: CGFloat = s / 2

            // lips
            ctx.setFillColor(UIColor(red: min(1, tr * 0.85 + 0.1), green: tg * 0.55, blue: tb * 0.55, alpha: 0.65).cgColor)
            ctx.fillEllipse(in: CGRect(x: uCenter - 34, y: vMouth - 9, width: 68, height: 19))

            // cheek blush
            ctx.setFillColor(UIColor(red: 0.85, green: 0.35, blue: 0.3, alpha: 0.10).cgColor)
            for du in [CGFloat(-58), CGFloat(58)] {
                ctx.fillEllipse(in: CGRect(x: uCenter + du - 34, y: vCheek - 26, width: 68, height: 52))
            }

            // subtle shading under the jaw (bottom of the texture)
            ctx.setFillColor(UIColor(red: tr * 0.8, green: tg * 0.75, blue: tb * 0.75, alpha: 0.35).cgColor)
            ctx.fill(CGRect(x: 0, y: s * 0.92, width: s, height: s * 0.08))
        }
        faceCache[k] = img
        return img
    }

    /// Streaky hair texture.
    static func hair(color: UIColor) -> UIImage {
        let k = key(color)
        if let cached = hairCache[k] { return cached }

        let img = Textures.image(256) { ctx, s in
            var rnd = SeededRandom(seed: 505)
            ctx.setFillColor(color.cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            var cr: CGFloat = 0, cg: CGFloat = 0, cb: CGFloat = 0, ca: CGFloat = 0
            color.getRed(&cr, green: &cg, blue: &cb, alpha: &ca)
            for _ in 0..<260 {
                let bright = rnd.next() < 0.45
                let f: CGFloat = bright ? 1.35 : 0.6
                ctx.setStrokeColor(UIColor(red: min(1, cr * f), green: min(1, cg * f),
                                           blue: min(1, cb * f), alpha: 0.35).cgColor)
                ctx.setLineWidth(CGFloat(rnd.range(0.7, 2.0)))
                let x = CGFloat(rnd.range(0, 256))
                let y = CGFloat(rnd.range(-10, 246))
                ctx.move(to: CGPoint(x: x, y: y))
                ctx.addLine(to: CGPoint(x: x + CGFloat(rnd.range(-6, 6)), y: y + CGFloat(rnd.range(14, 40))))
                ctx.strokePath()
            }
        }
        hairCache[k] = img
        return img
    }

    /// Woven wool texture for uniforms and dresses.
    static func cloth(color: UIColor) -> UIImage {
        let k = key(color)
        if let cached = clothCache[k] { return cached }

        let img = Textures.image(256) { ctx, s in
            var rnd = SeededRandom(seed: 606)
            ctx.setFillColor(color.cgColor)
            ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))
            var cr: CGFloat = 0, cg: CGFloat = 0, cb: CGFloat = 0, ca: CGFloat = 0
            color.getRed(&cr, green: &cg, blue: &cb, alpha: &ca)
            // fine weave
            for row in 0..<64 {
                let f: CGFloat = row % 2 == 0 ? 1.06 : 0.94
                ctx.setFillColor(UIColor(red: min(1, cr * f), green: min(1, cg * f),
                                         blue: min(1, cb * f), alpha: 0.5).cgColor)
                ctx.fill(CGRect(x: 0, y: CGFloat(row) * 4, width: s, height: 2))
            }
            // wear and folds
            for _ in 0..<80 {
                let bright = rnd.next() < 0.5
                let f: CGFloat = bright ? 1.15 : 0.85
                ctx.setFillColor(UIColor(red: min(1, cr * f), green: min(1, cg * f),
                                         blue: min(1, cb * f), alpha: 0.12).cgColor)
                let w = CGFloat(rnd.range(10, 60))
                ctx.fillEllipse(in: CGRect(x: CGFloat(rnd.range(0, 256)), y: CGFloat(rnd.range(0, 256)),
                                           width: w, height: w * 0.5))
            }
        }
        clothCache[k] = img
        return img
    }
}
