import SceneKit
import UIKit

enum HatStyle {
    case none
    case peakedCap
    case ladyHat
}

enum BeardStyle {
    case none
    case shortBeard   // Nicholas II
    case fullBeard    // Witte
    case bigBeard     // Alexander III
    case sideWhiskers // Pobedonostsev
}

struct PersonaSpec {
    var coatColor: UIColor = UIColor(red: 0.16, green: 0.22, blue: 0.18, alpha: 1)
    var trouserColor: UIColor = UIColor(white: 0.14, alpha: 1)
    var isDress: Bool = false
    var dressColor: UIColor = .white
    var hat: HatStyle = .none
    var hatColor: UIColor = UIColor(red: 0.13, green: 0.18, blue: 0.15, alpha: 1)
    var hairColor: UIColor = UIColor(red: 0.32, green: 0.22, blue: 0.13, alpha: 1)
    var bald: Bool = false
    var beard: BeardStyle = .none
    var beardColor: UIColor? = nil
    var skinColor: UIColor = UIColor(red: 0.93, green: 0.78, blue: 0.66, alpha: 1)
    var epaulettes: Bool = false
    var glasses: Bool = false
    var scale: Float = 1.0
}

/// A procedurally built humanoid with animatable limbs.
final class GameCharacter {
    let root = SCNNode()
    var leftArm: SCNNode?
    var rightArm: SCNNode?
    var leftLeg: SCNNode?
    var rightLeg: SCNNode?
    /// Materials that can be re-tinted at runtime (e.g. mourning dress).
    var clothMaterials: [SCNMaterial] = []
    private var walkPhase: Float = 0

    /// Drives a simple procedural walk cycle. speed is in m/s; 0 relaxes limbs.
    func updateWalk(dt: Float, speed: Float) {
        if speed > 0.05 {
            walkPhase += dt * (3.0 + speed * 2.2)
            let amp = min(speed / 3.0, 1.0) * 0.6
            let swing = sinf(walkPhase) * amp
            leftArm?.eulerAngles.x = swing
            rightArm?.eulerAngles.x = -swing
            leftLeg?.eulerAngles.x = -swing
            rightLeg?.eulerAngles.x = swing
        } else {
            leftArm?.eulerAngles.x *= 0.85
            rightArm?.eulerAngles.x *= 0.85
            leftLeg?.eulerAngles.x *= 0.85
            rightLeg?.eulerAngles.x *= 0.85
        }
    }
}

enum CharacterFactory {

    private static func mat(_ color: UIColor) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = color
        m.lightingModel = .blinn
        m.specular.contents = UIColor(white: 0.15, alpha: 1)
        return m
    }

    private static func part(_ geometry: SCNGeometry, _ material: SCNMaterial,
                             _ x: Float, _ y: Float, _ z: Float) -> SCNNode {
        geometry.materials = [material]
        let n = SCNNode(geometry: geometry)
        n.position = SCNVector3(x, y, z)
        return n
    }

    /// Builds a character facing +Z.
    static func make(_ s: PersonaSpec) -> GameCharacter {
        let c = GameCharacter()
        let skin = mat(s.skinColor)
        let coat = mat(s.coatColor)
        let hairMat = mat(s.hairColor)
        let beardMat = mat(s.beardColor ?? s.hairColor)
        let dark = mat(UIColor(white: 0.08, alpha: 1))
        let gold = mat(UIColor(red: 0.85, green: 0.68, blue: 0.2, alpha: 1))
        c.clothMaterials.append(coat)

        var armMat = coat

        if s.isDress {
            let dressMat = mat(s.dressColor)
            c.clothMaterials.append(dressMat)
            armMat = dressMat
            let skirt = part(SCNCone(topRadius: 0.17, bottomRadius: 0.44, height: 1.05), dressMat, 0, 0.525, 0)
            c.root.addChildNode(skirt)
            let bodice = part(SCNBox(width: 0.38, height: 0.48, length: 0.22, chamferRadius: 0.05), dressMat, 0, 1.25, 0)
            c.root.addChildNode(bodice)
        } else {
            let torso = part(SCNBox(width: 0.42, height: 0.6, length: 0.24, chamferRadius: 0.05), coat, 0, 1.22, 0)
            c.root.addChildNode(torso)
            // frock-coat skirt
            let coatSkirt = part(SCNBox(width: 0.44, height: 0.3, length: 0.26, chamferRadius: 0.04), coat, 0, 0.82, 0)
            c.root.addChildNode(coatSkirt)
            let belt = part(SCNBox(width: 0.44, height: 0.06, length: 0.26, chamferRadius: 0.01), dark, 0, 0.99, 0)
            c.root.addChildNode(belt)
            // uniform buttons
            var by: Float = 1.06
            while by < 1.45 {
                let button = part(SCNSphere(radius: 0.016), gold, 0, by, 0.125)
                c.root.addChildNode(button)
                by += 0.11
            }
            // legs
            let trousers = mat(s.trouserColor)
            for side in [Float(-1), Float(1)] {
                let pivot = SCNNode()
                pivot.position = SCNVector3(side * 0.11, 0.98, 0)
                let leg = part(SCNCapsule(capRadius: 0.065, height: 0.85), trousers, 0, -0.44, 0)
                pivot.addChildNode(leg)
                let boot = part(SCNBox(width: 0.11, height: 0.08, length: 0.2, chamferRadius: 0.02), dark, 0, -0.87, 0.03)
                pivot.addChildNode(boot)
                c.root.addChildNode(pivot)
                if side < 0 { c.leftLeg = pivot } else { c.rightLeg = pivot }
            }
        }

        // arms
        for side in [Float(-1), Float(1)] {
            let pivot = SCNNode()
            pivot.position = SCNVector3(side * 0.27, 1.46, 0)
            let arm = part(SCNCapsule(capRadius: 0.055, height: 0.55), armMat, 0, -0.28, 0)
            pivot.addChildNode(arm)
            let hand = part(SCNSphere(radius: 0.05), skin, 0, -0.56, 0)
            pivot.addChildNode(hand)
            c.root.addChildNode(pivot)
            if side < 0 { c.leftArm = pivot } else { c.rightArm = pivot }
        }

        if s.epaulettes {
            for side in [Float(-1), Float(1)] {
                let ep = part(SCNBox(width: 0.14, height: 0.03, length: 0.1, chamferRadius: 0.01), gold, side * 0.22, 1.54, 0)
                c.root.addChildNode(ep)
            }
        }

        // head assembly
        let headNode = SCNNode()
        headNode.position = SCNVector3(0, 1.66, 0)
        c.root.addChildNode(headNode)

        let neck = part(SCNCylinder(radius: 0.05, height: 0.1), skin, 0, -0.12, 0)
        headNode.addChildNode(neck)
        let head = part(SCNSphere(radius: 0.145), skin, 0, 0, 0)
        headNode.addChildNode(head)

        // eyes
        for side in [Float(-1), Float(1)] {
            let eye = part(SCNSphere(radius: 0.022), mat(.white), side * 0.055, 0.02, 0.115)
            headNode.addChildNode(eye)
            let pupil = part(SCNSphere(radius: 0.011), dark, side * 0.055, 0.02, 0.133)
            headNode.addChildNode(pupil)
        }
        // nose
        let nose = part(SCNBox(width: 0.03, height: 0.05, length: 0.045, chamferRadius: 0.01), skin, 0, -0.02, 0.135)
        headNode.addChildNode(nose)

        if !s.bald {
            let hair = part(SCNSphere(radius: 0.15), hairMat, 0, 0.03, -0.02)
            hair.scale = SCNVector3(1.0, 0.85, 1.0)
            headNode.addChildNode(hair)
        }

        switch s.beard {
        case .none:
            break
        case .shortBeard:
            let beard = part(SCNSphere(radius: 0.09), beardMat, 0, -0.085, 0.055)
            beard.scale = SCNVector3(0.95, 0.85, 0.72)
            headNode.addChildNode(beard)
            let mustache = part(SCNBox(width: 0.1, height: 0.028, length: 0.03, chamferRadius: 0.01), beardMat, 0, -0.048, 0.135)
            headNode.addChildNode(mustache)
        case .fullBeard:
            let beard = part(SCNSphere(radius: 0.1), beardMat, 0, -0.1, 0.05)
            beard.scale = SCNVector3(1.0, 1.05, 0.72)
            headNode.addChildNode(beard)
            let mustache = part(SCNBox(width: 0.11, height: 0.03, length: 0.03, chamferRadius: 0.01), beardMat, 0, -0.048, 0.135)
            headNode.addChildNode(mustache)
        case .bigBeard:
            let beard = part(SCNSphere(radius: 0.115), beardMat, 0, -0.135, 0.045)
            beard.scale = SCNVector3(1.05, 1.3, 0.75)
            headNode.addChildNode(beard)
            let mustache = part(SCNBox(width: 0.12, height: 0.032, length: 0.03, chamferRadius: 0.01), beardMat, 0, -0.048, 0.135)
            headNode.addChildNode(mustache)
        case .sideWhiskers:
            for side in [Float(-1), Float(1)] {
                let whisker = part(SCNBox(width: 0.035, height: 0.11, length: 0.07, chamferRadius: 0.01), beardMat, side * 0.125, -0.05, 0.03)
                headNode.addChildNode(whisker)
            }
        }

        switch s.hat {
        case .none:
            break
        case .peakedCap:
            let capMat = mat(s.hatColor)
            let band = part(SCNCylinder(radius: 0.155, height: 0.07), mat(UIColor(red: 0.6, green: 0.12, blue: 0.12, alpha: 1)), 0, 0.1, 0)
            headNode.addChildNode(band)
            let top = part(SCNCylinder(radius: 0.165, height: 0.045), capMat, 0, 0.155, 0)
            headNode.addChildNode(top)
            let visor = part(SCNBox(width: 0.2, height: 0.015, length: 0.1, chamferRadius: 0.005), dark, 0, 0.07, 0.14)
            headNode.addChildNode(visor)
        case .ladyHat:
            let hatMat = mat(s.hatColor)
            let crown = part(SCNCylinder(radius: 0.09, height: 0.09), hatMat, 0, 0.14, 0)
            headNode.addChildNode(crown)
            let brim = part(SCNCylinder(radius: 0.17, height: 0.015), hatMat, 0, 0.1, 0)
            headNode.addChildNode(brim)
        }

        if s.isDress {
            // hair bun
            let bun = part(SCNSphere(radius: 0.06), hairMat, 0, 0.04, -0.13)
            headNode.addChildNode(bun)
        }

        if s.glasses {
            let glassMat = mat(UIColor(white: 0.75, alpha: 1))
            for side in [Float(-1), Float(1)] {
                let rim = part(SCNTorus(ringRadius: 0.033, pipeRadius: 0.004), glassMat, side * 0.055, 0.02, 0.138)
                rim.eulerAngles.x = Float.pi / 2
                headNode.addChildNode(rim)
            }
        }

        c.root.scale = SCNVector3(s.scale, s.scale, s.scale)
        return c
    }

    // MARK: - Historical persona looks

    static func nicholasII() -> GameCharacter {
        var s = PersonaSpec()
        s.coatColor = UIColor(red: 0.15, green: 0.22, blue: 0.17, alpha: 1) // Preobrazhensky dark green
        s.hat = .peakedCap
        s.beard = .shortBeard
        s.hairColor = UIColor(red: 0.35, green: 0.24, blue: 0.14, alpha: 1)
        s.epaulettes = true
        s.scale = 0.98
        return make(s)
    }

    static func alexanderIII() -> GameCharacter {
        var s = PersonaSpec()
        s.coatColor = UIColor(red: 0.12, green: 0.15, blue: 0.22, alpha: 1)
        s.beard = .bigBeard
        s.beardColor = UIColor(red: 0.32, green: 0.24, blue: 0.16, alpha: 1)
        s.hairColor = UIColor(red: 0.3, green: 0.24, blue: 0.17, alpha: 1)
        s.hat = .peakedCap
        s.hatColor = UIColor(red: 0.1, green: 0.13, blue: 0.19, alpha: 1)
        s.epaulettes = true
        s.scale = 1.12 // the emperor was famously huge
        return make(s)
    }

    static func mariaFeodorovna() -> GameCharacter {
        var s = PersonaSpec()
        s.isDress = true
        s.dressColor = UIColor(red: 0.14, green: 0.18, blue: 0.32, alpha: 1)
        s.hairColor = UIColor(red: 0.2, green: 0.13, blue: 0.09, alpha: 1)
        s.hat = .ladyHat
        s.hatColor = UIColor(red: 0.14, green: 0.18, blue: 0.32, alpha: 1)
        s.scale = 0.92
        return make(s)
    }

    static func alexandra() -> GameCharacter {
        var s = PersonaSpec()
        s.isDress = true
        s.dressColor = UIColor(red: 0.9, green: 0.87, blue: 0.8, alpha: 1)
        s.hairColor = UIColor(red: 0.5, green: 0.3, blue: 0.15, alpha: 1)
        s.hat = .ladyHat
        s.hatColor = UIColor(white: 0.92, alpha: 1)
        s.scale = 0.99
        return make(s)
    }

    static func witte() -> GameCharacter {
        var s = PersonaSpec()
        s.coatColor = UIColor(white: 0.16, alpha: 1)
        s.beard = .fullBeard
        s.beardColor = UIColor(red: 0.42, green: 0.38, blue: 0.34, alpha: 1)
        s.hairColor = UIColor(red: 0.4, green: 0.36, blue: 0.32, alpha: 1)
        s.scale = 1.08 // Witte was very tall
        return make(s)
    }

    static func pobedonostsev() -> GameCharacter {
        var s = PersonaSpec()
        s.coatColor = UIColor(white: 0.1, alpha: 1)
        s.bald = true
        s.beard = .sideWhiskers
        s.beardColor = UIColor(white: 0.75, alpha: 1)
        s.glasses = true
        s.skinColor = UIColor(red: 0.88, green: 0.75, blue: 0.64, alpha: 1)
        s.scale = 0.96
        return make(s)
    }

    static func guardsman() -> GameCharacter {
        var s = PersonaSpec()
        s.coatColor = UIColor(red: 0.15, green: 0.22, blue: 0.17, alpha: 1)
        s.hat = .peakedCap
        s.beard = .shortBeard
        s.beardColor = UIColor(red: 0.25, green: 0.18, blue: 0.1, alpha: 1)
        s.epaulettes = true
        s.scale = 1.04
        return make(s)
    }
}
