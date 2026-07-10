import SceneKit
import UIKit

/// A minimal, fully-controlled Wavefront OBJ parser. We do NOT use Model I/O
/// for character meshes: it silently drops the object (`o`) and material
/// (`usemtl`) names we rely on for rigging and colouring. This parser keeps
/// every `o` group as a separate, correctly-named SCNNode whose geometry
/// carries one SCNGeometryElement per `usemtl`, with the material name
/// preserved verbatim.
enum ObjLoader {

    private struct Piece {
        var positions: [SCNVector3] = []
        var normals: [SCNVector3] = []
        var uvs: [CGPoint] = []
        var indexByKey: [String: Int32] = [:]
        // material name -> triangle indices
        var elements: [String: [Int32]] = [:]
        // preserves material appearance order
        var materialOrder: [String] = []
    }

    /// Loads the OBJ at `url` into a dictionary of objectName -> SCNNode.
    static func load(url: URL) -> [String: SCNNode] {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [:] }

        var positions: [SCNVector3] = []
        var normals: [SCNVector3] = []
        var uvs: [CGPoint] = []

        var pieces: [String: Piece] = [:]
        var order: [String] = []
        var currentObject = "default"
        var currentMaterial = "default"
        pieces[currentObject] = Piece()
        order.append(currentObject)

        text.enumerateLines { line, _ in
            if line.hasPrefix("v ") {
                let c = line.split(separator: " ")
                if c.count >= 4 {
                    positions.append(SCNVector3(Float(c[1]) ?? 0, Float(c[2]) ?? 0, Float(c[3]) ?? 0))
                }
            } else if line.hasPrefix("vn ") {
                let c = line.split(separator: " ")
                if c.count >= 4 {
                    normals.append(SCNVector3(Float(c[1]) ?? 0, Float(c[2]) ?? 0, Float(c[3]) ?? 0))
                }
            } else if line.hasPrefix("vt ") {
                let c = line.split(separator: " ")
                if c.count >= 3 {
                    uvs.append(CGPoint(x: CGFloat(Float(c[1]) ?? 0), y: CGFloat(Float(c[2]) ?? 0)))
                }
            } else if line.hasPrefix("o ") {
                currentObject = String(line.dropFirst(2))
                if pieces[currentObject] == nil {
                    pieces[currentObject] = Piece()
                    order.append(currentObject)
                }
            } else if line.hasPrefix("usemtl ") {
                currentMaterial = String(line.dropFirst(7))
            } else if line.hasPrefix("f ") {
                let verts = line.split(separator: " ").dropFirst()
                var faceIdx: [Int32] = []
                for token in verts {
                    faceIdx.append(vertexIndex(String(token), &pieces[currentObject]!,
                                               positions, normals, uvs))
                }
                // triangulate as a fan
                guard faceIdx.count >= 3 else { return }
                var p = pieces[currentObject]!
                if p.elements[currentMaterial] == nil {
                    p.elements[currentMaterial] = []
                    p.materialOrder.append(currentMaterial)
                }
                for i in 1..<(faceIdx.count - 1) {
                    p.elements[currentMaterial]!.append(contentsOf: [faceIdx[0], faceIdx[i], faceIdx[i + 1]])
                }
                pieces[currentObject] = p
            }
        }

        var result: [String: SCNNode] = [:]
        for name in order {
            guard let piece = pieces[name], !piece.positions.isEmpty,
                  !piece.elements.isEmpty else { continue }
            let node = SCNNode(geometry: buildGeometry(piece))
            node.name = name
            result[name] = node
        }
        return result
    }

    private static func vertexIndex(_ token: String, _ piece: inout Piece,
                                    _ positions: [SCNVector3], _ normals: [SCNVector3],
                                    _ uvs: [CGPoint]) -> Int32 {
        if let cached = piece.indexByKey[token] { return cached }
        let parts = token.split(separator: "/", omittingEmptySubsequences: false)
        func resolve(_ s: Substring?, _ count: Int) -> Int {
            guard let s = s, let raw = Int(s) else { return -1 }
            return raw > 0 ? raw - 1 : count + raw   // OBJ is 1-based; negatives are relative
        }
        let vi = parts.count > 0 ? resolve(parts[0], positions.count) : -1
        let ti = parts.count > 1 ? resolve(parts[1], uvs.count) : -1
        let ni = parts.count > 2 ? resolve(parts[2], normals.count) : -1

        let newIndex = Int32(piece.positions.count)
        piece.positions.append((vi >= 0 && vi < positions.count) ? positions[vi] : SCNVector3(0, 0, 0))
        piece.normals.append((ni >= 0 && ni < normals.count) ? normals[ni] : SCNVector3(0, 1, 0))
        piece.uvs.append((ti >= 0 && ti < uvs.count) ? uvs[ti] : CGPoint(x: 0, y: 0))
        piece.indexByKey[token] = newIndex
        return newIndex
    }

    private static func buildGeometry(_ piece: Piece) -> SCNGeometry {
        let vSrc = SCNGeometrySource(vertices: piece.positions)
        let nSrc = SCNGeometrySource(normals: piece.normals)
        let tSrc = SCNGeometrySource(textureCoordinates: piece.uvs)

        var elements: [SCNGeometryElement] = []
        var materials: [SCNMaterial] = []
        for matName in piece.materialOrder {
            guard let indices = piece.elements[matName] else { continue }
            elements.append(SCNGeometryElement(indices: indices, primitiveType: .triangles))
            let m = SCNMaterial()
            m.name = matName
            materials.append(m)
        }
        let geo = SCNGeometry(sources: [vSrc, nSrc, tSrc], elements: elements)
        geo.materials = materials
        return geo
    }
}
