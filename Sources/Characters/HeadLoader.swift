import SceneKit
import ModelIO
import SceneKit.ModelIO
import UIKit

/// Loads sculpted heads produced by the cloud Blender pipeline
/// (MPFB2/MakeHuman -> morph targets -> Cycles-baked skin -> OBJ).
/// The mesh is a real anatomical human head; this loader normalizes it
/// (centers the skull, scales to the rig's head slot) and re-binds
/// materials to the bundled textures.
enum HeadLoader {

    private static var cache: [String: SCNNode] = [:]

    static func bundleImage(_ fileName: String) -> UIImage? {
        guard let url = Bundle.main.url(forResource: fileName, withExtension: nil, subdirectory: "Models") else {
            return nil
        }
        return UIImage(contentsOfFile: url.path)
    }

    /// Returns a normalized head node: skull centered at the origin,
    /// face looking along +Z, total height = targetHeight.
    static func load(named name: String, targetHeight: Float,
                     skinTexture: String, eyeTexture: String) -> SCNNode? {
        if let cached = cache[name] {
            return cached.clone()
        }
        guard let url = Bundle.main.url(forResource: name, withExtension: "obj", subdirectory: "Models") else {
            return nil
        }
        let asset = MDLAsset(url: url)
        asset.loadTextures()
        let scene = SCNScene(mdlAsset: asset)

        let container = SCNNode()
        for child in scene.rootNode.childNodes {
            container.addChildNode(child)
        }

        // normalize: bbox center to origin, uniform scale to target height
        let (minV, maxV) = container.boundingBox
        let height = maxV.y - minV.y
        guard height > 0.01 else { return nil }
        let scale = targetHeight / height
        container.scale = SCNVector3(scale, scale, scale)
        container.position = SCNVector3(-(minV.x + maxV.x) / 2 * scale,
                                        -(minV.y + maxV.y) / 2 * scale,
                                        -(minV.z + maxV.z) / 2 * scale)

        let wrapper = SCNNode()
        wrapper.name = "sculptedHead"
        wrapper.addChildNode(container)

        // re-bind materials: named textures from the bundle + engine shaders
        let skinImage = bundleImage(skinTexture)
        let eyeImage = bundleImage(eyeTexture)
        wrapper.enumerateChildNodes { node, _ in
            guard let geo = node.geometry else { return }
            let nodeName = (node.name ?? "").lowercased()
            for m in geo.materials {
                m.lightingModel = .blinn
                if nodeName.contains("low-poly") || nodeName.contains("eye") {
                    if let img = eyeImage { m.diffuse.contents = img }
                    m.specular.contents = UIColor(white: 0.6, alpha: 1)
                    m.shininess = 0.8
                } else if nodeName.contains("hair") || nodeName.contains("beard")
                            || nodeName.contains("mustache") || nodeName.contains("brows") {
                    m.specular.contents = UIColor(white: 0.05, alpha: 1)
                } else {
                    if let img = skinImage { m.diffuse.contents = img }
                    m.specular.contents = UIColor(white: 0.15, alpha: 1)
                    ShaderLibrary.applySkin(m)
                }
            }
        }

        cache[name] = wrapper
        return wrapper.clone()
    }
}
