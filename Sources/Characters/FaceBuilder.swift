import SceneKit
import UIKit

/// Anatomical parameters of a face. Every historical figure gets his own
/// set of values — this is the game's "portrait sculptor".
struct FaceSpec {
    // skull proportions (radii in meters)
    var headWidth: Float = 0.095
    var headHeight: Float = 0.118
    var headDepth: Float = 0.103

    // sculpting strengths
    var browRidge: Float = 0.0060
    var eyeSocketDepth: Float = 0.0055
    var cheekbone: Float = 0.0050
    var noseRidge: Float = 0.0085
    var noseTip: Float = 0.011
    var chin: Float = 0.0080
    var jawNarrowing: Float = 0.22       // 0 = square jaw, higher = narrower

    // coloring
    var skinTone = UIColor(red: 0.91, green: 0.76, blue: 0.65, alpha: 1)
    var eyeColor = UIColor(red: 0.45, green: 0.55, blue: 0.62, alpha: 1)
    var hairColor = UIColor(red: 0.33, green: 0.23, blue: 0.13, alpha: 1)
    var beardColor: UIColor? = nil

    // hair coverage
    var bald: Bool = false
    var hasMustache: Bool = false
    var hasShortBeard: Bool = false      // Nicholas II style
    var hasBigBeard: Bool = false        // Alexander III style
    var hasSideWhiskers: Bool = false    // Pobedonostsev style
    var femaleHair: Bool = false         // bun at the back
    var glasses: Bool = false
}

/// Builds a sculpted, textured head as a node. The head node's origin is
/// the skull center; the character faces +Z.
enum FaceBuilder {

    // face landmark latitudes (theta: 0 = crown, pi = under the chin)
    private static let browTheta: Float = 1.28
    private static let eyeTheta: Float = 1.50
    private static let cheekTheta: Float = 1.82
    private static let noseTipTheta: Float = 1.86
    private static let mouthTheta: Float = 2.24
    private static let chinTheta: Float = 2.56

    /// The sculpted skull surface for a given spec.
    static func headPosition(_ spec: FaceSpec, _ theta: Float, _ phi: Float) -> SCNVector3 {
        let st = sinf(theta)
        var x = st * sinf(phi) * spec.headWidth
        var y = cosf(theta) * spec.headHeight
        var z = st * cosf(phi) * spec.headDepth

        // direction for displacement (radial, horizontal-ish for face features)
        let len = sqrtf(x * x + y * y + z * z)
        let nx = x / max(len, 0.0001)
        let ny = y / max(len, 0.0001)
        let nz = z / max(len, 0.0001)

        var d: Float = 0
        let front = MeshBuilder.bump(phi, center: 0, width: 1.1)

        // brow ridge
        d += spec.browRidge * MeshBuilder.bump(theta, center: browTheta, width: 0.16) * MeshBuilder.bump(phi, center: 0, width: 0.55)
        // eye sockets (both sides)
        d -= spec.eyeSocketDepth * MeshBuilder.bump(theta, center: eyeTheta, width: 0.17)
            * (MeshBuilder.bump(phi, center: 0.42, width: 0.24) + MeshBuilder.bump(phi, center: -0.42, width: 0.24))
        // cheekbones
        d += spec.cheekbone * MeshBuilder.bump(theta, center: cheekTheta, width: 0.30)
            * (MeshBuilder.bump(phi, center: 0.68, width: 0.34) + MeshBuilder.bump(phi, center: -0.68, width: 0.34))
        // nose ridge running down the face center
        d += spec.noseRidge * MeshBuilder.bump(theta, center: 1.70, width: 0.30) * MeshBuilder.bump(phi, center: 0, width: 0.14)
        // nose tip
        d += spec.noseTip * MeshBuilder.bump(theta, center: noseTipTheta, width: 0.13) * MeshBuilder.bump(phi, center: 0, width: 0.14)
        // philtrum dip
        d -= 0.004 * MeshBuilder.bump(theta, center: 2.06, width: 0.09) * MeshBuilder.bump(phi, center: 0, width: 0.16)
        // chin
        d += spec.chin * MeshBuilder.bump(theta, center: chinTheta, width: 0.28) * MeshBuilder.bump(phi, center: 0, width: 0.38)
        // slight occiput (back of the skull)
        d += 0.004 * MeshBuilder.bump(theta, center: 1.1, width: 0.5) * MeshBuilder.bump(phi, center: Float.pi, width: 0.9)
        d += 0.004 * MeshBuilder.bump(theta, center: 1.1, width: 0.5) * MeshBuilder.bump(phi, center: -Float.pi, width: 0.9)

        x += nx * d
        y += ny * d
        z += nz * d

        // jaw narrowing below the cheeks
        if theta > 1.9 {
            let t = min((theta - 1.9) / 0.9, 1.0)
            let narrow = 1.0 - spec.jawNarrowing * t * (1.0 - 0.55 * front)
            x *= narrow
            // pull the lower back of the head in toward the neck
            let backPull = 1.0 - 0.28 * t * (1.0 - front)
            z *= backPull
        }

        return SCNVector3(x, y, z)
    }

    static func build(_ spec: FaceSpec) -> SCNNode {
        let head = SCNNode()
        head.name = "head"

        let skinMat = SCNMaterial()
        skinMat.diffuse.contents = SkinTextures.face(tone: spec.skinTone)
        skinMat.lightingModel = .blinn
        skinMat.specular.contents = UIColor(white: 0.18, alpha: 1)
        skinMat.shininess = 0.3
        ShaderLibrary.applySkin(skinMat)

        // --- skull ---
        let skullMesh = MeshBuilder.parametricShell(
            rings: 42, segments: 48,
            thetaRange: 0...Float.pi,
            phiRange: (-Float.pi)...Float.pi
        ) { theta, phi in
            headPosition(spec, theta, phi)
        }
        head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: skullMesh, material: skinMat)))

        // --- eyes ---
        let whiteMat = SCNMaterial()
        whiteMat.diffuse.contents = UIColor(red: 0.97, green: 0.96, blue: 0.94, alpha: 1)
        whiteMat.lightingModel = .blinn
        let irisMat = SCNMaterial()
        irisMat.diffuse.contents = spec.eyeColor
        irisMat.lightingModel = .blinn
        let pupilMat = SCNMaterial()
        pupilMat.diffuse.contents = UIColor(white: 0.04, alpha: 1)

        for side in [Float(-1), Float(1)] {
            let socket = headPosition(spec, eyeTheta, side * 0.42)
            // bury most of the eyeball in the socket: only a shallow cap shows
            let eyePivot = SCNNode()
            eyePivot.position = SCNVector3(socket.x * 0.78, socket.y * 0.78, socket.z * 0.78)
            eyePivot.eulerAngles.y = atan2f(socket.x, socket.z) * 0.55
            head.addChildNode(eyePivot)

            let ballGeo = SCNSphere(radius: 0.0205)
            ballGeo.materials = [whiteMat]
            eyePivot.addChildNode(SCNNode(geometry: ballGeo))

            let irisGeo = SCNCylinder(radius: 0.0105, height: 0.0022)
            irisGeo.materials = [irisMat]
            let iris = SCNNode(geometry: irisGeo)
            iris.position = SCNVector3(0, 0, 0.0195)
            iris.eulerAngles.x = Float.pi / 2
            eyePivot.addChildNode(iris)

            let pupilGeo = SCNCylinder(radius: 0.0045, height: 0.0026)
            pupilGeo.materials = [pupilMat]
            let pupil = SCNNode(geometry: pupilGeo)
            pupil.position = SCNVector3(0, 0, 0.0201)
            pupil.eulerAngles.x = Float.pi / 2
            eyePivot.addChildNode(pupil)
        }

        // --- eyebrows ---
        let hairMat = SCNMaterial()
        hairMat.diffuse.contents = SkinTextures.hair(color: spec.hairColor)
        hairMat.lightingModel = .blinn
        for side in [Float(-1), Float(1)] {
            let browPos = headPosition(spec, browTheta + 0.08, side * 0.40)
            let browGeo = SCNBox(width: 0.045, height: 0.0075, length: 0.012, chamferRadius: 0.003)
            browGeo.materials = [hairMat]
            let brow = SCNNode(geometry: browGeo)
            brow.position = SCNVector3(browPos.x, browPos.y, browPos.z + 0.002)
            brow.eulerAngles.z = -side * 0.12
            brow.eulerAngles.y = side * 0.25
            head.addChildNode(brow)
        }

        // --- ears ---
        for side in [Float(-1), Float(1)] {
            let earGeo = SCNSphere(radius: 0.024)
            earGeo.materials = [skinMat]
            let ear = SCNNode(geometry: earGeo)
            ear.position = SCNVector3(side * spec.headWidth * 0.97, -0.008, -0.008)
            ear.scale = SCNVector3(0.35, 1.0, 0.62)
            head.addChildNode(ear)
        }

        // --- hair ---
        let hairShellMat = SCNMaterial()
        hairShellMat.diffuse.contents = SkinTextures.hair(color: spec.hairColor)
        hairShellMat.lightingModel = .blinn
        if !spec.bald {
            // crown cap
            let cap = MeshBuilder.parametricShell(
                rings: 14, segments: 40,
                thetaRange: 0...1.12,
                phiRange: (-Float.pi)...Float.pi
            ) { theta, phi in
                let p = headPosition(spec, theta, phi)
                return SCNVector3(p.x * 1.045, p.y * 1.045 + 0.001, p.z * 1.045)
            }
            head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: cap, material: hairShellMat)))
            // sides and back, leaving the face open
            let back = MeshBuilder.parametricShell(
                rings: 12, segments: 36,
                thetaRange: 1.10...1.85,
                phiRange: 1.15...(2 * Float.pi - 1.15)
            ) { theta, phi in
                let p = headPosition(spec, theta, phi)
                return SCNVector3(p.x * 1.04, p.y * 1.04, p.z * 1.04)
            }
            head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: back, material: hairShellMat)))
        }
        if spec.femaleHair {
            let bunGeo = SCNSphere(radius: 0.052)
            bunGeo.materials = [hairShellMat]
            let bun = SCNNode(geometry: bunGeo)
            bun.position = SCNVector3(0, 0.02, -spec.headDepth * 0.95)
            head.addChildNode(bun)
        }

        // --- facial hair ---
        let beardMat = SCNMaterial()
        beardMat.diffuse.contents = SkinTextures.hair(color: spec.beardColor ?? spec.hairColor)
        beardMat.lightingModel = .blinn

        if spec.hasShortBeard || spec.hasBigBeard {
            let big = spec.hasBigBeard
            let beard = MeshBuilder.parametricShell(
                rings: 16, segments: 34,
                thetaRange: 1.95...(big ? 2.95 : 2.85),
                phiRange: -1.35...1.35
            ) { theta, phi in
                // hide the shell inside the head around the mouth opening
                let mouthZone = MeshBuilder.bump(theta, center: mouthTheta, width: 0.13) * MeshBuilder.bump(phi, center: 0, width: 0.38)
                let scale: Float = mouthZone > 0.5 ? 0.975 : (big ? 1.10 : 1.055)
                let p = headPosition(spec, theta, phi)
                var out = SCNVector3(p.x * scale, p.y * scale, p.z * scale)
                // the beard grows downward at the chin
                let chinZone = MeshBuilder.bump(theta, center: 2.8, width: 0.35) * MeshBuilder.bump(phi, center: 0, width: 0.6)
                out.y -= chinZone * (big ? 0.055 : 0.018)
                return out
            }
            head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: beard, material: beardMat)))
        }

        if spec.hasMustache || spec.hasShortBeard || spec.hasBigBeard {
            let mustache = MeshBuilder.parametricShell(
                rings: 6, segments: 20,
                thetaRange: 2.02...2.20,
                phiRange: -0.62...0.62
            ) { theta, phi in
                let p = headPosition(spec, theta, phi)
                let flare = 1.06 + 0.02 * MeshBuilder.bump(phi, center: 0, width: 0.3)
                return SCNVector3(p.x * flare, p.y * flare, p.z * flare)
            }
            head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: mustache, material: beardMat)))
        }

        if spec.hasSideWhiskers {
            for side in [Float(-1), Float(1)] {
                let whiskers = MeshBuilder.parametricShell(
                    rings: 8, segments: 12,
                    thetaRange: 1.55...2.45,
                    phiRange: (side * 0.85 - 0.35)...(side * 0.85 + 0.35)
                ) { theta, phi in
                    let p = headPosition(spec, theta, phi)
                    return SCNVector3(p.x * 1.06, p.y * 1.06, p.z * 1.06)
                }
                head.addChildNode(SCNNode(geometry: MeshBuilder.geometry(from: whiskers, material: beardMat)))
            }
        }

        // --- glasses ---
        if spec.glasses {
            let rimMat = SCNMaterial()
            rimMat.diffuse.contents = UIColor(white: 0.7, alpha: 1)
            for side in [Float(-1), Float(1)] {
                let socket = headPosition(spec, eyeTheta, side * 0.42)
                let rimGeo = SCNTorus(ringRadius: 0.017, pipeRadius: 0.0016)
                rimGeo.materials = [rimMat]
                let rim = SCNNode(geometry: rimGeo)
                rim.position = SCNVector3(socket.x, socket.y, socket.z + 0.012)
                rim.eulerAngles.x = Float.pi / 2
                head.addChildNode(rim)
            }
            let bridgeGeo = SCNBox(width: 0.03, height: 0.002, length: 0.002, chamferRadius: 0)
            bridgeGeo.materials = [rimMat]
            let bridge = SCNNode(geometry: bridgeGeo)
            let noseP = headPosition(spec, eyeTheta, 0)
            bridge.position = SCNVector3(0, noseP.y, noseP.z + 0.013)
            head.addChildNode(bridge)
        }

        return head
    }
}
