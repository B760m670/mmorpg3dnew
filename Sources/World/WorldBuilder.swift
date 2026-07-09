import SceneKit
import UIKit

/// Builds Palace Square, St. Petersburg, as it stood in 1894:
/// the Winter Palace (in its historical terracotta-red paint of the era),
/// the Alexander Column, the General Staff Building, gas lamps and snow.
enum WorldBuilder {

    static func tiled(_ image: UIImage, _ rx: Float, _ ry: Float) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = image
        m.diffuse.wrapS = .repeat
        m.diffuse.wrapT = .repeat
        m.diffuse.contentsTransform = SCNMatrix4MakeScale(rx, ry, 1)
        m.lightingModel = .blinn
        m.specular.contents = UIColor(white: 0.1, alpha: 1)
        return m
    }

    static func plain(_ color: UIColor) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = color
        m.lightingModel = .blinn
        m.specular.contents = UIColor(white: 0.12, alpha: 1)
        return m
    }

    static func node(_ g: SCNGeometry, _ m: SCNMaterial, _ x: Float, _ y: Float, _ z: Float) -> SCNNode {
        g.materials = [m]
        let n = SCNNode(geometry: g)
        n.position = SCNVector3(x, y, z)
        return n
    }

    /// Builds the whole world into the scene; returns obstacles for movement.
    static func build(into scene: SCNScene) -> [Collider] {
        var colliders: [Collider] = []
        let root = scene.rootNode

        // --- ground ---
        let groundGeo = SCNPlane(width: 500, height: 500)
        let groundMat = tiled(Textures.cobblestone, 70, 70)
        ShaderLibrary.applyFrost(groundMat)
        groundGeo.materials = [groundMat]
        let ground = SCNNode(geometry: groundGeo)
        ground.name = "ground"
        ground.eulerAngles.x = -Float.pi / 2
        root.addChildNode(ground)

        // --- Winter Palace (north side) ---
        let palace = buildPalaceFacade(width: 190, height: 20, depth: 28,
                                       wall: Textures.palaceWall,
                                       windowRows: [4.5, 12.0])
        palace.position = SCNVector3(0, 0, -69)
        root.addChildNode(palace.flattenedClone())
        colliders.append(Collider(minX: -96, maxX: 96, minZ: -90, maxZ: -54))

        // --- General Staff Building (south side, two wings + arch) ---
        let staffWest = buildPalaceFacade(width: 82, height: 15, depth: 20,
                                          wall: Textures.staffWall,
                                          windowRows: [3.5, 9.5], facesNorth: true)
        staffWest.position = SCNVector3(-50, 0, 66)
        root.addChildNode(staffWest.flattenedClone())
        let staffEast = buildPalaceFacade(width: 82, height: 15, depth: 20,
                                          wall: Textures.staffWall,
                                          windowRows: [3.5, 9.5], facesNorth: true)
        staffEast.position = SCNVector3(50, 0, 66)
        root.addChildNode(staffEast.flattenedClone())
        // triumphal arch bridging the wings
        let archNode = SCNNode()
        let archTop = node(SCNBox(width: 20, height: 6, length: 20, chamferRadius: 0),
                           tiled(Textures.staffWall, 4, 2), 0, 12, 66)
        archNode.addChildNode(archTop)
        for side in [Float(-1), Float(1)] {
            let pillar = node(SCNBox(width: 3, height: 9, length: 20, chamferRadius: 0),
                              tiled(Textures.staffWall, 1, 2), side * 8.5, 4.5, 66)
            archNode.addChildNode(pillar)
        }
        // chariot of Glory silhouette on top of the arch
        let chariotBase = node(SCNBox(width: 8, height: 0.6, length: 3, chamferRadius: 0),
                               plain(UIColor(white: 0.2, alpha: 1)), 0, 15.3, 66)
        archNode.addChildNode(chariotBase)
        let bronze = plain(UIColor(red: 0.18, green: 0.22, blue: 0.2, alpha: 1))
        for i in 0..<6 {
            let horse = node(SCNBox(width: 0.8, height: 1.6, length: 2.2, chamferRadius: 0.2),
                             bronze, -3.0 + Float(i) * 1.2, 16.4, 66)
            archNode.addChildNode(horse)
        }
        let victory = node(SCNCone(topRadius: 0.1, bottomRadius: 0.6, height: 2.6),
                           bronze, 0, 17.0, 67.5)
        archNode.addChildNode(victory)
        root.addChildNode(archNode.flattenedClone())
        colliders.append(Collider(minX: -96, maxX: 96, minZ: 55, maxZ: 90))

        // --- Alexander Column (center of the square) ---
        let column = buildAlexanderColumn()
        root.addChildNode(column)
        colliders.append(Collider(minX: -5, maxX: 5, minZ: -5, maxZ: 5))

        // bollards ring around the column
        let bollardMat = plain(UIColor(white: 0.08, alpha: 1))
        for i in 0..<12 {
            let a = Float(i) / 12 * 2 * Float.pi
            let b = node(SCNCylinder(radius: 0.18, height: 0.9), bollardMat,
                         sinf(a) * 11, 0.45, cosf(a) * 11)
            root.addChildNode(b)
        }

        // --- gas lamps ---
        let lampPositions: [(Float, Float, Bool)] = [
            (-25, -20, true), (25, -20, true), (-25, 25, true), (25, 25, true),
            (-60, 0, false), (60, 0, false), (0, -48, true), (-60, 45, false), (60, 45, false)
        ]
        for (x, z, lit) in lampPositions {
            root.addChildNode(buildLamp(x: x, z: z, withLight: lit))
        }

        // --- trees at the western edge (Admiralty garden) ---
        var rnd = SeededRandom(seed: 99)
        let treeCluster = SCNNode()
        for i in 0..<14 {
            let x = Float(-110) + Float(rnd.range(-8, 8))
            let z = Float(-45) + Float(i) * 8 + Float(rnd.range(-3, 3))
            treeCluster.addChildNode(buildFirTree(x: x, z: z, scale: Float(rnd.range(0.8, 1.4))))
        }
        for i in 0..<14 {
            let x = Float(110) + Float(rnd.range(-8, 8))
            let z = Float(-45) + Float(i) * 8 + Float(rnd.range(-3, 3))
            treeCluster.addChildNode(buildFirTree(x: x, z: z, scale: Float(rnd.range(0.8, 1.4))))
        }
        root.addChildNode(treeCluster.flattenedClone())

        // --- falling snow ---
        let snow = SCNParticleSystem()
        snow.birthRate = 220
        snow.particleLifeSpan = 14
        snow.particleSize = 0.06
        snow.particleSizeVariation = 0.04
        snow.particleVelocity = 1.6
        snow.particleVelocityVariation = 0.8
        snow.emittingDirection = SCNVector3(0, -1, 0)
        snow.spreadingAngle = 20
        snow.particleImage = Textures.snowflake
        snow.particleColor = .white
        snow.emitterShape = SCNBox(width: 140, height: 1, length: 140, chamferRadius: 0)
        let snowNode = SCNNode()
        snowNode.name = "snow"
        snowNode.position = SCNVector3(0, 24, 0)
        snowNode.addParticleSystem(snow)
        root.addChildNode(snowNode)

        // --- atmosphere ---
        scene.fogStartDistance = 60
        scene.fogEndDistance = 280
        scene.fogDensityExponent = 1.5

        return colliders
    }

    /// A long classicist facade with pilasters, two rows of windows,
    /// cornice and roofline statues.
    private static func buildPalaceFacade(width: Float, height: Float, depth: Float,
                                          wall: UIImage, windowRows: [Float],
                                          facesNorth: Bool = false) -> SCNNode {
        let building = SCNNode()
        let wallMat = tiled(wall, width / 6, height / 6)
        let white = plain(UIColor(white: 0.9, alpha: 1))
        let windowMat = plain(UIColor.white)
        windowMat.diffuse.contents = Textures.windowGlass
        windowMat.lightingModel = .blinn
        windowMat.emission.contents = UIColor(red: 0.25, green: 0.18, blue: 0.06, alpha: 1)

        let body = node(SCNBox(width: CGFloat(width), height: CGFloat(height), length: CGFloat(depth), chamferRadius: 0),
                        wallMat, 0, height / 2, 0)
        building.addChildNode(body)

        // Facade layers are strictly separated in depth (>= 5 cm gaps between
        // parallel faces) to keep the depth buffer stable at long distances.
        let sign: Float = facesNorth ? -1 : 1
        let wallZ: Float = sign * depth / 2

        var x = -width / 2 + 4
        while x <= width / 2 - 4 {
            // pilaster: front sticks out 0.40 m, back is buried in the wall
            let pilaster = node(SCNBox(width: 1.0, height: CGFloat(height - 3), length: 0.5, chamferRadius: 0),
                                white, x - 3, (height - 3) / 2 + 1, wallZ + sign * 0.15)
            building.addChildNode(pilaster)
            // windows: white frame plate on the wall, glass panel in front of it,
            // every parallel-face pair separated by >= 2 cm
            for rowY in windowRows {
                let frame = node(SCNBox(width: 3.0, height: 4.4, length: 0.10, chamferRadius: 0),
                                 white, x, rowY, wallZ + sign * 0.09)
                building.addChildNode(frame)
                let win = node(SCNBox(width: 2.4, height: 3.8, length: 0.12, chamferRadius: 0),
                               windowMat, x, rowY, wallZ + sign * 0.22)
                building.addChildNode(win)
            }
            x += 6
        }

        // base strip and cornice
        let base = node(SCNBox(width: CGFloat(width + 1), height: 1.4, length: CGFloat(depth + 1), chamferRadius: 0),
                        white, 0, 0.7, 0)
        building.addChildNode(base)
        let cornice = node(SCNBox(width: CGFloat(width + 1.5), height: 0.9, length: CGFloat(depth + 1.5), chamferRadius: 0),
                           white, 0, height - 0.5, 0)
        building.addChildNode(cornice)

        // roof
        let roof = node(SCNBox(width: CGFloat(width), height: 1.2, length: CGFloat(depth), chamferRadius: 0),
                        plain(UIColor(red: 0.25, green: 0.32, blue: 0.3, alpha: 1)), 0, height + 0.6, 0)
        building.addChildNode(roof)

        // roofline statues (simplified silhouettes)
        var sx = -width / 2 + 8
        let statueMat = plain(UIColor(white: 0.35, alpha: 1))
        let statueZ: Float = facesNorth ? -depth / 2 + 1 : depth / 2 - 1
        while sx <= width / 2 - 8 {
            let statue = node(SCNBox(width: 0.5, height: 1.6, length: 0.5, chamferRadius: 0.15),
                              statueMat, sx, height + 2.0, statueZ)
            building.addChildNode(statue)
            sx += 12
        }

        return building
    }

    /// The Alexander Column: stepped granite base, monolithic shaft,
    /// and the angel with the cross on top.
    private static func buildAlexanderColumn() -> SCNNode {
        let column = SCNNode()
        let granite = tiled(Textures.granite, 2, 2)
        let bronze = plain(UIColor(red: 0.22, green: 0.26, blue: 0.23, alpha: 1))

        // stepped base
        let step1 = node(SCNBox(width: 8.5, height: 0.6, length: 8.5, chamferRadius: 0), granite, 0, 0.3, 0)
        column.addChildNode(step1)
        let step2 = node(SCNBox(width: 7, height: 0.6, length: 7, chamferRadius: 0), granite, 0, 0.9, 0)
        column.addChildNode(step2)
        // pedestal with bronze reliefs
        let pedestal = node(SCNBox(width: 4.6, height: 4.4, length: 4.6, chamferRadius: 0.05), granite, 0, 3.4, 0)
        column.addChildNode(pedestal)
        for side in 0..<4 {
            let relief = node(SCNBox(width: 3.4, height: 3.0, length: 0.15, chamferRadius: 0.05), bronze, 0, 3.4, 0)
            let a = Float(side) * Float.pi / 2
            relief.position = SCNVector3(sinf(a) * 2.35, 3.4, cosf(a) * 2.35)
            relief.eulerAngles.y = a
            column.addChildNode(relief)
        }
        // shaft — the tallest monolith in the world
        let shaft = node(SCNCylinder(radius: 1.55, height: 23.5), granite, 0, 5.6 + 11.75, 0)
        column.addChildNode(shaft)
        // capital
        let capital = node(SCNCylinder(radius: 2.0, height: 1.2), bronze, 0, 29.7, 0)
        column.addChildNode(capital)
        let abacus = node(SCNBox(width: 4.2, height: 0.7, length: 4.2, chamferRadius: 0.05), bronze, 0, 30.6, 0)
        column.addChildNode(abacus)
        // angel with cross
        let angelBase = node(SCNCylinder(radius: 0.8, height: 1.6), bronze, 0, 31.7, 0)
        column.addChildNode(angelBase)
        let angelBody = node(SCNCone(topRadius: 0.15, bottomRadius: 0.55, height: 2.2), bronze, 0, 33.6, 0)
        column.addChildNode(angelBody)
        let angelHead = node(SCNSphere(radius: 0.3), bronze, 0, 34.9, 0)
        column.addChildNode(angelHead)
        for side in [Float(-1), Float(1)] {
            let wing = node(SCNBox(width: 1.2, height: 1.6, length: 0.15, chamferRadius: 0.3), bronze, side * 0.8, 33.9, -0.3)
            wing.eulerAngles.z = side * 0.5
            column.addChildNode(wing)
        }
        let crossV = node(SCNBox(width: 0.12, height: 2.6, length: 0.12, chamferRadius: 0), bronze, 0.5, 34.5, 0.3)
        crossV.eulerAngles.z = -0.5
        column.addChildNode(crossV)
        let crossH = node(SCNBox(width: 1.1, height: 0.12, length: 0.12, chamferRadius: 0), bronze, 0.8, 35.0, 0.3)
        crossH.eulerAngles.z = -0.5
        column.addChildNode(crossH)

        return column.flattenedClone()
    }

    private static func buildLamp(x: Float, z: Float, withLight: Bool) -> SCNNode {
        let lamp = SCNNode()
        lamp.position = SCNVector3(x, 0, z)
        let iron = plain(UIColor(white: 0.06, alpha: 1))
        let pole = node(SCNCylinder(radius: 0.09, height: 4.2), iron, 0, 2.1, 0)
        lamp.addChildNode(pole)
        let foot = node(SCNCylinder(radius: 0.3, height: 0.5), iron, 0, 0.25, 0)
        lamp.addChildNode(foot)
        let glassGeo = SCNSphere(radius: 0.28)
        let glassMat = SCNMaterial()
        glassMat.diffuse.contents = UIColor(red: 1.0, green: 0.85, blue: 0.55, alpha: 1)
        glassMat.emission.contents = UIColor(red: 1.0, green: 0.8, blue: 0.45, alpha: 1)
        glassGeo.materials = [glassMat]
        let glass = SCNNode(geometry: glassGeo)
        glass.position = SCNVector3(0, 4.4, 0)
        lamp.addChildNode(glass)
        let cap = node(SCNCone(topRadius: 0.02, bottomRadius: 0.34, height: 0.35), iron, 0, 4.8, 0)
        lamp.addChildNode(cap)
        if withLight {
            let light = SCNLight()
            light.type = .omni
            light.color = UIColor(red: 1.0, green: 0.78, blue: 0.5, alpha: 1)
            light.intensity = 400
            light.attenuationStartDistance = 2
            light.attenuationEndDistance = 22
            glass.light = light
        }
        return lamp
    }

    private static func buildFirTree(x: Float, z: Float, scale: Float) -> SCNNode {
        let tree = SCNNode()
        tree.position = SCNVector3(x, 0, z)
        tree.scale = SCNVector3(scale, scale, scale)
        let trunkMat = plain(UIColor(red: 0.25, green: 0.17, blue: 0.1, alpha: 1))
        let leafMat = plain(UIColor(red: 0.1, green: 0.25, blue: 0.14, alpha: 1))
        let snowyMat = plain(UIColor(red: 0.75, green: 0.82, blue: 0.8, alpha: 1))
        let trunk = node(SCNCylinder(radius: 0.25, height: 2.2), trunkMat, 0, 1.1, 0)
        tree.addChildNode(trunk)
        let tier1 = node(SCNCone(topRadius: 0.1, bottomRadius: 2.2, height: 2.6), leafMat, 0, 2.8, 0)
        tree.addChildNode(tier1)
        let tier2 = node(SCNCone(topRadius: 0.05, bottomRadius: 1.7, height: 2.2), leafMat, 0, 4.4, 0)
        tree.addChildNode(tier2)
        let tier3 = node(SCNCone(topRadius: 0.0, bottomRadius: 1.2, height: 1.9), snowyMat, 0, 5.9, 0)
        tree.addChildNode(tier3)
        return tree
    }
}
