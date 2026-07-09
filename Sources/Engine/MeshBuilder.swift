import SceneKit
import UIKit

/// Procedural polygon-mesh generator. This is the game's "sculpting studio":
/// heads, torsos and limbs are built as real triangle meshes with smooth
/// normals and UVs, generated entirely in code.
enum MeshBuilder {

    struct MeshData {
        var vertices: [SCNVector3] = []
        var uvs: [CGPoint] = []
        var indices: [Int32] = []
    }

    /// Turns raw mesh data into an SCNGeometry with smooth (accumulated) normals.
    static func geometry(from mesh: MeshData, material: SCNMaterial) -> SCNGeometry {
        var normals = [SCNVector3](repeating: SCNVector3(0, 0, 0), count: mesh.vertices.count)
        var i = 0
        while i + 2 < mesh.indices.count {
            let ia = Int(mesh.indices[i])
            let ib = Int(mesh.indices[i + 1])
            let ic = Int(mesh.indices[i + 2])
            let a = mesh.vertices[ia]
            let b = mesh.vertices[ib]
            let c = mesh.vertices[ic]
            let ab = b - a
            let ac = c - a
            let n = SCNVector3(ab.y * ac.z - ab.z * ac.y,
                               ab.z * ac.x - ab.x * ac.z,
                               ab.x * ac.y - ab.y * ac.x)
            normals[ia] = normals[ia] + n
            normals[ib] = normals[ib] + n
            normals[ic] = normals[ic] + n
            i += 3
        }
        let normalized: [SCNVector3] = normals.map { n in
            let l = n.length
            if l > 0.000001 {
                return SCNVector3(n.x / l, n.y / l, n.z / l)
            }
            return SCNVector3(0, 1, 0)
        }

        let vSrc = SCNGeometrySource(vertices: mesh.vertices)
        let nSrc = SCNGeometrySource(normals: normalized)
        let tSrc = SCNGeometrySource(textureCoordinates: mesh.uvs)
        let element = SCNGeometryElement(indices: mesh.indices, primitiveType: .triangles)
        let g = SCNGeometry(sources: [vSrc, nSrc, tSrc], elements: [element])
        g.materials = [material]
        return g
    }

    /// Parametric grid surface: theta sweeps rows (v), phi sweeps columns (u).
    /// `position` returns the 3D point for a given (theta, phi) — this is where
    /// all the sculpting happens (skulls, jaws, brows, beard shells, ...).
    static func parametricShell(rings: Int, segments: Int,
                                thetaRange: ClosedRange<Float>,
                                phiRange: ClosedRange<Float>,
                                position: (Float, Float) -> SCNVector3) -> MeshData {
        var mesh = MeshData()
        let cols = segments + 1
        for ring in 0...rings {
            let tv = Float(ring) / Float(rings)
            let theta = thetaRange.lowerBound + (thetaRange.upperBound - thetaRange.lowerBound) * tv
            for seg in 0...segments {
                let tu = Float(seg) / Float(segments)
                let phi = phiRange.lowerBound + (phiRange.upperBound - phiRange.lowerBound) * tu
                mesh.vertices.append(position(theta, phi))
                mesh.uvs.append(CGPoint(x: CGFloat(tu), y: CGFloat(tv)))
            }
        }
        for ring in 0..<rings {
            for seg in 0..<segments {
                let a = Int32(ring * cols + seg)
                let b = a + 1
                let c = Int32((ring + 1) * cols + seg)
                let d = c + 1
                mesh.indices.append(contentsOf: [a, c, b, b, c, d])
            }
        }
        return mesh
    }

    /// Surface of revolution with an elliptical cross-section — used for
    /// torsos and limbs (chest taper, waist, calf muscles, boot flares).
    /// profile: pairs of (y, radius) from top to bottom.
    static func lathe(profile: [(y: Float, r: Float)], segments: Int,
                      depthRatio: Float = 1.0) -> MeshData {
        var mesh = MeshData()
        let rows = profile.count
        let cols = segments + 1
        for (row, p) in profile.enumerated() {
            for seg in 0...segments {
                let tu = Float(seg) / Float(segments)
                let phi = tu * 2 * Float.pi - Float.pi
                mesh.vertices.append(SCNVector3(p.r * sinf(phi), p.y, p.r * cosf(phi) * depthRatio))
                mesh.uvs.append(CGPoint(x: CGFloat(tu), y: CGFloat(row) / CGFloat(max(rows - 1, 1))))
            }
        }
        for row in 0..<(rows - 1) {
            for seg in 0..<segments {
                let a = Int32(row * cols + seg)
                let b = a + 1
                let c = Int32((row + 1) * cols + seg)
                let d = c + 1
                mesh.indices.append(contentsOf: [a, c, b, b, c, d])
            }
        }
        return mesh
    }

    /// Gaussian falloff used as the sculpting brush.
    static func bump(_ v: Float, center: Float, width: Float) -> Float {
        let d = (v - center) / width
        return expf(-d * d)
    }
}
