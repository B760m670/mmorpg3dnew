import SceneKit
import UIKit

/// Body proportions and dress of a realistic character.
struct BodySpec {
    var overallScale: Float = 1.0
    var shoulderHalfWidth: Float = 0.215
    var stoutness: Float = 1.0           // 1.0 slim … 1.25 heavyset

    var tunicColor = UIColor(red: 0.14, green: 0.21, blue: 0.16, alpha: 1)
    var trouserColor = UIColor(red: 0.10, green: 0.12, blue: 0.14, alpha: 1)
    var bootColor = UIColor(white: 0.07, alpha: 1)
    var collarColor: UIColor? = UIColor(red: 0.62, green: 0.10, blue: 0.10, alpha: 1)
    var cuffColor: UIColor? = UIColor(red: 0.62, green: 0.10, blue: 0.10, alpha: 1)
    var epaulettes: Bool = false
    var doubleButtonRow: Bool = false
    var medals: Bool = false
    var beltAndBuckle: Bool = false
    var highBoots: Bool = false

    // dress instead of trousers (empresses)
    var isDress: Bool = false
    var dressColor = UIColor(white: 0.9, alpha: 1)

    // peaked cap
    var peakedCap: Bool = false
    var capColor = UIColor(red: 0.12, green: 0.19, blue: 0.14, alpha: 1)
    var capBandColor = UIColor(red: 0.62, green: 0.10, blue: 0.10, alpha: 1)
    var ladyHat: Bool = false
    var ladyHatColor = UIColor(white: 0.92, alpha: 1)
}

/// Assembles a full realistic character: sculpted head (FaceBuilder) +
/// lathe-meshed body with a two-segment limb rig.
enum HumanBody {

    private static func mat(_ image: UIImage) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = image
        m.lightingModel = .blinn
        m.specular.contents = UIColor(white: 0.1, alpha: 1)
        return m
    }

    private static func plainMat(_ color: UIColor) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = color
        m.lightingModel = .blinn
        m.specular.contents = UIColor(white: 0.15, alpha: 1)
        return m
    }

    private static func latheNode(_ profile: [(y: Float, r: Float)], _ material: SCNMaterial,
                                  depthRatio: Float = 1.0, segments: Int = 22) -> SCNNode {
        let mesh = MeshBuilder.lathe(profile: profile, segments: segments, depthRatio: depthRatio)
        return SCNNode(geometry: MeshBuilder.geometry(from: mesh, material: material))
    }

    static func make(face: FaceSpec, body: BodySpec) -> GameCharacter {
        let c = GameCharacter()
        let stout = body.stoutness

        let tunicMat = mat(SkinTextures.cloth(color: body.tunicColor))
        c.clothMaterials.append(tunicMat)
        let trouserMat = mat(SkinTextures.cloth(color: body.trouserColor))
        let bootMat = plainMat(body.bootColor)
        let skinMat = plainMat(face.skinTone)
        let goldMat = plainMat(UIColor(red: 0.85, green: 0.68, blue: 0.2, alpha: 1))

        // ---------- legs (attached to the root so the pelvis can bob) ----------
        if !body.isDress {
            for side in [Float(-1), Float(1)] {
                let hip = SCNNode()
                hip.position = SCNVector3(side * 0.10 * stout, 0.94, 0)
                c.root.addChildNode(hip)

                let thigh = latheNode([
                    (0.025, 0.0),
                    (0.02, 0.088 * stout),
                    (-0.20, 0.078 * stout),
                    (-0.44, 0.060 * stout)
                ], trouserMat, depthRatio: 1.05)
                hip.addChildNode(thigh)

                let knee = SCNNode()
                knee.position = SCNVector3(0, -0.46, 0)
                hip.addChildNode(knee)

                let lowerMat = body.highBoots ? bootMat : trouserMat
                let shin = latheNode([
                    (0.025, 0.0),
                    (0.02, 0.062 * stout),
                    (-0.06, 0.068 * stout),   // boot flare / calf
                    (-0.26, 0.052 * stout),
                    (-0.44, 0.048 * stout),
                    (-0.445, 0.0)
                ], lowerMat, depthRatio: 1.0)
                knee.addChildNode(shin)

                let footGeo = SCNBox(width: 0.09, height: 0.05, length: 0.22, chamferRadius: 0.02)
                footGeo.materials = [bootMat]
                let foot = SCNNode(geometry: footGeo)
                foot.position = SCNVector3(0, -0.455, 0.055)
                knee.addChildNode(foot)

                if side < 0 { c.leftLeg = hip; c.leftKnee = knee } else { c.rightLeg = hip; c.rightKnee = knee }
            }
        }

        // ---------- pelvis and torso ----------
        let pelvis = SCNNode()
        pelvis.position = SCNVector3(0, 0.98, 0)
        c.root.addChildNode(pelvis)
        c.pelvis = pelvis
        c.basePelvisY = 0.98

        if body.isDress {
            let dressMat = mat(SkinTextures.cloth(color: body.dressColor))
            c.clothMaterials.append(dressMat)
            // floor-length skirt
            let skirt = latheNode([
                (0.14, 0.150 * stout),
                (-0.30, 0.26 * stout),
                (-0.75, 0.36 * stout),
                (-0.96, 0.40 * stout),
                (-0.97, 0.0)
            ], dressMat, depthRatio: 0.85, segments: 30)
            pelvis.addChildNode(skirt)
            // bodice
            let bodice = latheNode([
                (0.10, 0.148 * stout),
                (0.26, 0.152 * stout),
                (0.44, 0.168 * stout),
                (0.55, 0.150 * stout),
                (0.60, 0.095),
                (0.64, 0.052)
            ], dressMat, depthRatio: 0.66)
            pelvis.addChildNode(bodice)
        } else {
            // military tunic with a frock-coat skirt hiding the hip joints
            let torso = latheNode([
                (-0.16, 0.165 * stout),
                (-0.02, 0.160 * stout),
                (0.12, 0.148 * stout),
                (0.32, 0.170 * stout),
                (0.48, 0.188 * stout),
                (0.56, 0.168 * stout),
                (0.60, 0.100),
                (0.64, 0.054)
            ], tunicMat, depthRatio: 0.62)
            pelvis.addChildNode(torso)
        }

        // collar
        if let collarColor = body.collarColor {
            let collarGeo = SCNCylinder(radius: 0.057, height: 0.038)
            collarGeo.materials = [plainMat(collarColor)]
            let collar = SCNNode(geometry: collarGeo)
            collar.position = SCNVector3(0, 0.645, 0)
            pelvis.addChildNode(collar)
        }

        // neck
        let neckGeo = SCNCylinder(radius: 0.045, height: 0.09)
        neckGeo.materials = [skinMat]
        let neck = SCNNode(geometry: neckGeo)
        neck.position = SCNVector3(0, 0.685, 0)
        pelvis.addChildNode(neck)

        // buttons
        if !body.isDress {
            let rows: [Float] = body.doubleButtonRow ? [-0.036, 0.036] : [0]
            for rowX in rows {
                var by: Float = 0.04
                while by < 0.50 {
                    // front z of the torso profile, approximately
                    let frontZ = 0.165 * stout * 0.62 + 0.006
                    let btnGeo = SCNSphere(radius: 0.011)
                    btnGeo.materials = [goldMat]
                    let btn = SCNNode(geometry: btnGeo)
                    btn.position = SCNVector3(rowX, by, frontZ)
                    pelvis.addChildNode(btn)
                    by += 0.085
                }
            }
        }

        // belt with buckle
        if body.beltAndBuckle {
            let beltGeo = SCNCylinder(radius: CGFloat(0.152 * stout), height: 0.045)
            beltGeo.materials = [plainMat(UIColor(red: 0.2, green: 0.13, blue: 0.08, alpha: 1))]
            let belt = SCNNode(geometry: beltGeo)
            belt.position = SCNVector3(0, 0.05, 0)
            belt.scale = SCNVector3(1, 1, 0.64)
            pelvis.addChildNode(belt)
            let buckleGeo = SCNBox(width: 0.045, height: 0.035, length: 0.01, chamferRadius: 0.005)
            buckleGeo.materials = [goldMat]
            let buckle = SCNNode(geometry: buckleGeo)
            buckle.position = SCNVector3(0, 0.05, 0.152 * stout * 0.64 + 0.004)
            pelvis.addChildNode(buckle)
        }

        // epaulettes / shoulder boards
        if body.epaulettes {
            for side in [Float(-1), Float(1)] {
                let epGeo = SCNBox(width: 0.055, height: 0.012, length: 0.11, chamferRadius: 0.005)
                epGeo.materials = [goldMat]
                let ep = SCNNode(geometry: epGeo)
                ep.position = SCNVector3(side * body.shoulderHalfWidth * 0.88, 0.575, 0)
                ep.eulerAngles.z = -side * 0.18
                ep.eulerAngles.y = Float.pi / 2
                pelvis.addChildNode(ep)
            }
        }

        // medals on the left breast
        if body.medals {
            let frontZ = 0.176 * stout * 0.62
            let crossGeo = SCNBox(width: 0.016, height: 0.016, length: 0.004, chamferRadius: 0.002)
            crossGeo.materials = [plainMat(UIColor(white: 0.92, alpha: 1))]
            let cross = SCNNode(geometry: crossGeo)
            cross.position = SCNVector3(-0.07, 0.40, frontZ)
            pelvis.addChildNode(cross)
            let medalGeo = SCNCylinder(radius: 0.009, height: 0.004)
            medalGeo.materials = [goldMat]
            let medal = SCNNode(geometry: medalGeo)
            medal.position = SCNVector3(-0.045, 0.40, frontZ)
            medal.eulerAngles.x = Float.pi / 2
            pelvis.addChildNode(medal)
        }

        // ---------- arms ----------
        let sleeveMat: SCNMaterial
        if body.isDress {
            sleeveMat = mat(SkinTextures.cloth(color: body.dressColor))
        } else {
            sleeveMat = tunicMat
        }

        for side in [Float(-1), Float(1)] {
            let shoulder = SCNNode()
            shoulder.position = SCNVector3(side * body.shoulderHalfWidth, 0.52, 0)
            pelvis.addChildNode(shoulder)

            let upperArm = latheNode([
                (0.045, 0.0),
                (0.04, 0.055 * stout),
                (-0.16, 0.048 * stout),
                (-0.30, 0.042 * stout)
            ], sleeveMat)
            shoulder.addChildNode(upperArm)

            let elbow = SCNNode()
            elbow.position = SCNVector3(0, -0.30, 0)
            shoulder.addChildNode(elbow)

            let forearm = latheNode([
                (0.015, 0.0),
                (0.01, 0.043 * stout),
                (-0.14, 0.038 * stout),
                (-0.25, 0.034 * stout),
                (-0.255, 0.0)
            ], sleeveMat)
            elbow.addChildNode(forearm)

            if let cuffColor = body.cuffColor, !body.isDress {
                let cuffGeo = SCNCylinder(radius: CGFloat(0.037 * stout), height: 0.05)
                cuffGeo.materials = [plainMat(cuffColor)]
                let cuff = SCNNode(geometry: cuffGeo)
                cuff.position = SCNVector3(0, -0.23, 0)
                elbow.addChildNode(cuff)
            }

            let handGeo = SCNSphere(radius: 0.040)
            handGeo.materials = [skinMat]
            let hand = SCNNode(geometry: handGeo)
            hand.position = SCNVector3(0, -0.285, 0.005)
            hand.scale = SCNVector3(0.8, 1.2, 0.55)
            elbow.addChildNode(hand)

            if side < 0 { c.leftArm = shoulder; c.leftElbow = elbow } else { c.rightArm = shoulder; c.rightElbow = elbow }
        }

        // ---------- head ----------
        let headAssembly = SCNNode()
        headAssembly.position = SCNVector3(0, 0.80, 0)
        pelvis.addChildNode(headAssembly)
        c.headNode = headAssembly

        let head = FaceBuilder.build(face)
        headAssembly.addChildNode(head)

        if body.peakedCap {
            let capMat = mat(SkinTextures.cloth(color: body.capColor))
            let bandGeo = SCNCylinder(radius: CGFloat(face.headWidth * 1.14), height: 0.045)
            bandGeo.materials = [plainMat(body.capBandColor)]
            let band = SCNNode(geometry: bandGeo)
            band.position = SCNVector3(0, 0.078, 0)
            headAssembly.addChildNode(band)

            let crown = latheNode([
                (0.057, 0.0),
                (0.055, face.headWidth * 1.30),
                (0.050, face.headWidth * 1.28),
                (0.015, face.headWidth * 1.10),
                (0.0, face.headWidth * 1.12)
            ], capMat)
            crown.position = SCNVector3(0, 0.10, 0.006)
            headAssembly.addChildNode(crown)

            let visorGeo = SCNCylinder(radius: 0.085, height: 0.007)
            visorGeo.materials = [plainMat(UIColor(white: 0.05, alpha: 1))]
            let visor = SCNNode(geometry: visorGeo)
            visor.position = SCNVector3(0, 0.058, face.headDepth * 0.9)
            visor.scale = SCNVector3(1.1, 1, 0.85)
            visor.eulerAngles.x = -0.12
            headAssembly.addChildNode(visor)

            // cockade
            let cockadeGeo = SCNCylinder(radius: 0.011, height: 0.004)
            cockadeGeo.materials = [plainMat(UIColor(red: 0.9, green: 0.6, blue: 0.1, alpha: 1))]
            let cockade = SCNNode(geometry: cockadeGeo)
            cockade.position = SCNVector3(0, 0.078, face.headDepth * 1.14)
            cockade.eulerAngles.x = Float.pi / 2
            headAssembly.addChildNode(cockade)
        }

        if body.ladyHat {
            let hatMat = plainMat(body.ladyHatColor)
            let crownGeo = SCNCylinder(radius: 0.075, height: 0.075)
            crownGeo.materials = [hatMat]
            let crown = SCNNode(geometry: crownGeo)
            crown.position = SCNVector3(0, 0.125, 0)
            headAssembly.addChildNode(crown)
            let brimGeo = SCNCylinder(radius: 0.135, height: 0.012)
            brimGeo.materials = [hatMat]
            let brim = SCNNode(geometry: brimGeo)
            brim.position = SCNVector3(0, 0.09, 0)
            headAssembly.addChildNode(brim)
        }

        c.root.scale = SCNVector3(body.overallScale, body.overallScale, body.overallScale)
        return c
    }
}
