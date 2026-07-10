import SceneKit
import ModelIO
import SceneKit.ModelIO
import UIKit

/// Joint coordinates exported by the Blender pipeline (joints.json, OBJ axes).
struct RigJoints: Decodable {
    let neck: [Float]
    let shoulder_l: [Float]
    let shoulder_r: [Float]
    let elbow_l: [Float]
    let elbow_r: [Float]
    let wrist_l: [Float]
    let wrist_r: [Float]
    let hip_l: [Float]
    let hip_r: [Float]
    let knee_l: [Float]
    let knee_r: [Float]
    let pelvis: [Float]
    let height: Float
}

/// Loads a full-body character produced by the cloud Blender pipeline:
/// a real MakeHuman-based anatomical mesh. When the mesh is segmented into
/// named pieces (head, torso, limbs) it is re-assembled onto an animatable
/// joint rig; otherwise it loads as a single static model so the character
/// is always visible.
enum SegmentedCharacter {

    /// Resource files may sit either at the bundle root or under a "Models"
    /// subdirectory, depending on how the build phase flattened them. Look in
    /// both so loading never depends on that detail.
    static func findURL(_ name: String, _ ext: String) -> URL? {
        if let u = Bundle.main.url(forResource: name, withExtension: ext) { return u }
        if let u = Bundle.main.url(forResource: name, withExtension: ext, subdirectory: "Models") { return u }
        return nil
    }

    /// Diagnostic string listing which model files the running app can see.
    static func diagnostics() -> String {
        let names = ["nicholas_uniform.obj", "nicholas_body.obj", "joints.json",
                     "nicholas_skin.png", "nicholas_eyes.png"]
        var found: [String] = []
        var missing: [String] = []
        for n in names {
            let parts = n.split(separator: ".")
            let base = String(parts[0]); let ext = String(parts[1])
            if findURL(base, ext) != nil { found.append(n) } else { missing.append(n) }
        }
        return "найдено: \(found.count)/\(names.count)" + (missing.isEmpty ? "" : " • нет: \(missing.joined(separator: ", "))")
    }

    static func loadJoints() -> RigJoints? {
        guard let url = findURL("joints", "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(RigJoints.self, from: data)
    }

    private static func bundleImage(_ fileName: String) -> UIImage? {
        let parts = fileName.split(separator: ".")
        guard parts.count == 2, let url = findURL(String(parts[0]), String(parts[1])) else { return nil }
        return UIImage(contentsOfFile: url.path)
    }

    /// Loads the OBJ, returning the scene and the named geometry pieces.
    private static func loadScene(_ objName: String) -> (SCNScene, [String: SCNNode])? {
        guard let url = findURL(objName, "obj") else { return nil }
        let asset = MDLAsset(url: url)
        asset.loadTextures()
        let scene = SCNScene(mdlAsset: asset)
        var pieces: [String: SCNNode] = [:]
        scene.rootNode.enumerateChildNodes { node, _ in
            if let name = node.name, node.geometry != nil {
                pieces[name] = node
            }
        }
        return (scene, pieces)
    }

    static func make(objName: String) -> GameCharacter? {
        guard let (scene, pieces) = loadScene(objName) else { return nil }

        let c = GameCharacter()

        // Rig only if the expected named pieces are present; otherwise fall
        // back to a single static model so the figure is always shown.
        if let joints = loadJoints(), pieces["torso"] != nil {
            assembleRig(c, pieces: pieces, joints: joints)
        } else {
            for child in scene.rootNode.childNodes {
                child.removeFromParentNode()
                c.root.addChildNode(child)
            }
        }

        applyMaterials(to: c.root)
        return c
    }

    private static func assembleRig(_ c: GameCharacter, pieces: [String: SCNNode], joints: RigJoints) {
        func v(_ a: [Float]) -> SCNVector3 { return SCNVector3(a[0], a[1], a[2]) }

        func wrap(_ pieceName: String, parent: SCNNode, parentWorld: SCNVector3,
                  jointWorld: SCNVector3) -> SCNNode {
            let w = SCNNode()
            w.position = jointWorld - parentWorld
            if let piece = pieces[pieceName] {
                piece.removeFromParentNode()
                piece.position = SCNVector3(-jointWorld.x, -jointWorld.y, -jointWorld.z)
                w.addChildNode(piece)
            }
            parent.addChildNode(w)
            return w
        }

        let pelvisWorld = SCNVector3(0, joints.pelvis[1], 0)
        let pelvis = SCNNode()
        pelvis.position = pelvisWorld
        c.root.addChildNode(pelvis)
        c.pelvis = pelvis
        c.basePelvisY = joints.pelvis[1]

        if let torso = pieces["torso"] {
            torso.removeFromParentNode()
            torso.position = SCNVector3(0, -pelvisWorld.y, 0)
            pelvis.addChildNode(torso)
        }

        c.headNode = wrap("head", parent: pelvis, parentWorld: pelvisWorld, jointWorld: v(joints.neck))

        let shoulderL = wrap("upperarm_l", parent: pelvis, parentWorld: pelvisWorld, jointWorld: v(joints.shoulder_l))
        let elbowL = wrap("forearm_l", parent: shoulderL, parentWorld: v(joints.shoulder_l), jointWorld: v(joints.elbow_l))
        _ = wrap("hand_l", parent: elbowL, parentWorld: v(joints.elbow_l), jointWorld: v(joints.wrist_l))
        c.leftArm = shoulderL
        c.leftElbow = elbowL

        let shoulderR = wrap("upperarm_r", parent: pelvis, parentWorld: pelvisWorld, jointWorld: v(joints.shoulder_r))
        let elbowR = wrap("forearm_r", parent: shoulderR, parentWorld: v(joints.shoulder_r), jointWorld: v(joints.elbow_r))
        _ = wrap("hand_r", parent: elbowR, parentWorld: v(joints.elbow_r), jointWorld: v(joints.wrist_r))
        c.rightArm = shoulderR
        c.rightElbow = elbowR

        let hipL = wrap("thigh_l", parent: c.root, parentWorld: SCNVector3(0, 0, 0), jointWorld: v(joints.hip_l))
        c.leftKnee = wrap("shin_l", parent: hipL, parentWorld: v(joints.hip_l), jointWorld: v(joints.knee_l))
        c.leftLeg = hipL

        let hipR = wrap("thigh_r", parent: c.root, parentWorld: SCNVector3(0, 0, 0), jointWorld: v(joints.hip_r))
        c.rightKnee = wrap("shin_r", parent: hipR, parentWorld: v(joints.hip_r), jointWorld: v(joints.knee_r))
        c.rightLeg = hipR

        // rest pose: bring the A-pose arms down to the sides
        shoulderL.eulerAngles.z = -0.52
        shoulderR.eulerAngles.z = 0.52
    }

    private static func applyMaterials(to root: SCNNode) {
        let skinImage = bundleImage("nicholas_skin.png")
        let eyeImage = bundleImage("nicholas_eyes.png")
        root.enumerateChildNodes { node, _ in
            guard let geo = node.geometry else { return }
            for m in geo.materials {
                let name = (m.name ?? "").lowercased()
                m.lightingModel = .blinn
                if name.contains("skin") {
                    if let img = skinImage { m.diffuse.contents = img }
                    m.specular.contents = UIColor(white: 0.16, alpha: 1)
                    ShaderLibrary.applySkin(m)
                } else if name.contains("eye") {
                    if let img = eyeImage { m.diffuse.contents = img }
                    m.specular.contents = UIColor(white: 0.7, alpha: 1)
                    m.shininess = 0.9
                } else if name.contains("gold") {
                    m.specular.contents = UIColor(white: 0.9, alpha: 1)
                    m.shininess = 0.7
                } else if name.contains("hair") || name.contains("beard")
                            || name.contains("mustache") || name.contains("brows") {
                    m.specular.contents = UIColor(white: 0.04, alpha: 1)
                } else {
                    m.specular.contents = UIColor(white: 0.08, alpha: 1)
                    ShaderLibrary.applyCloth(m)
                }
            }
        }
    }
}
