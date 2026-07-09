import UIKit

/// On-screen thumbstick. `vector` is normalized: x right, y forward (up).
final class VirtualJoystick: UIView {

    private let base = UIView()
    private let thumb = UIView()
    private(set) var vector = CGPoint.zero

    override init(frame: CGRect) {
        super.init(frame: frame)
        isMultipleTouchEnabled = false
        backgroundColor = .clear

        base.isUserInteractionEnabled = false
        base.backgroundColor = UIColor(white: 1, alpha: 0.12)
        base.layer.borderColor = UIColor(white: 1, alpha: 0.35).cgColor
        base.layer.borderWidth = 2
        addSubview(base)

        thumb.isUserInteractionEnabled = false
        thumb.backgroundColor = UIColor(white: 1, alpha: 0.4)
        addSubview(thumb)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layoutSubviews() {
        super.layoutSubviews()
        let d = min(bounds.width, bounds.height)
        base.frame = CGRect(x: (bounds.width - d) / 2, y: (bounds.height - d) / 2, width: d, height: d)
        base.layer.cornerRadius = d / 2
        let td = d * 0.4
        if vector == .zero {
            thumb.frame = CGRect(x: (bounds.width - td) / 2, y: (bounds.height - td) / 2, width: td, height: td)
        }
        thumb.layer.cornerRadius = td / 2
    }

    private func handle(_ touches: Set<UITouch>) {
        guard let t = touches.first else { return }
        let p = t.location(in: self)
        let center = CGPoint(x: bounds.midX, y: bounds.midY)
        var dx = p.x - center.x
        var dy = p.y - center.y
        let radius = min(bounds.width, bounds.height) / 2 - 10
        let len = sqrt(dx * dx + dy * dy)
        if len > radius {
            dx = dx / len * radius
            dy = dy / len * radius
        }
        thumb.center = CGPoint(x: center.x + dx, y: center.y + dy)
        vector = CGPoint(x: dx / radius, y: -dy / radius)
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) { handle(touches) }
    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) { handle(touches) }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) { reset() }
    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) { reset() }

    private func reset() {
        vector = .zero
        UIView.animate(withDuration: 0.15) {
            self.thumb.center = CGPoint(x: self.bounds.midX, y: self.bounds.midY)
        }
    }
}
