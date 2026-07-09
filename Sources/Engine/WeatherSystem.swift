import SceneKit
import UIKit

/// Living weather driven by the historical calendar: Petersburg winters
/// bury the square in snow, spring thins it out, summer clears the stones,
/// autumn drowns the city in fog. Wind gusts sway the falling snow.
final class WeatherSystem: EngineSystem {
    let systemName = "Погода"

    enum Season {
        case winter, spring, summer, autumn

        static func forMonth(_ m: Int) -> Season {
            switch m {
            case 11, 12, 1, 2: return .winter
            case 3, 4: return .spring
            case 5, 6, 7, 8: return .summer
            default: return .autumn
            }
        }
    }

    private var currentSeason: Season?
    private var windTime: Float = 0

    func update(dt: Float, context: EngineContext) {
        windTime += dt

        let season = Season.forMonth(context.clock.month)
        let snowNode = context.scene.rootNode.childNode(withName: "snow", recursively: false)

        if season != currentSeason {
            currentSeason = season
            apply(season, scene: context.scene, snowNode: snowNode)
        }

        // wind gusts push the snowfall sideways
        if let ps = snowNode?.particleSystems?.first, ps.birthRate > 0 {
            let gust = sinf(windTime * 0.23) * 0.9 + sinf(windTime * 0.071) * 0.5
            ps.acceleration = SCNVector3(gust, -0.3, sinf(windTime * 0.13) * 0.4)
        }
    }

    private func apply(_ season: Season, scene: SCNScene, snowNode: SCNNode?) {
        let ps = snowNode?.particleSystems?.first
        let ground = scene.rootNode.childNode(withName: "ground", recursively: false)
        let groundMat = ground?.geometry?.firstMaterial

        switch season {
        case .winter:
            ps?.birthRate = 260
            groundMat?.diffuse.contents = Textures.cobblestone
            scene.fogStartDistance = 55
            scene.fogEndDistance = 260
        case .spring:
            ps?.birthRate = 50
            groundMat?.diffuse.contents = Textures.cobblestone
            scene.fogStartDistance = 80
            scene.fogEndDistance = 320
        case .summer:
            ps?.birthRate = 0
            groundMat?.diffuse.contents = Textures.cobblestoneSummer
            scene.fogStartDistance = 130
            scene.fogEndDistance = 460
        case .autumn:
            ps?.birthRate = 0
            groundMat?.diffuse.contents = Textures.cobblestoneSummer
            scene.fogStartDistance = 45
            scene.fogEndDistance = 210
        }
    }
}
