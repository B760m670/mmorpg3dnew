import SceneKit

/// Frame context passed to every engine subsystem.
struct EngineContext {
    let scene: SCNScene
    let clock: HistoryClock
    let playerPosition: SCNVector3
}

/// A pluggable engine subsystem (weather, story, crowds, ...).
/// Each subsystem lives in its own file and never touches the others.
protocol EngineSystem: AnyObject {
    var systemName: String { get }
    func update(dt: Float, context: EngineContext)
}

/// РомановЪ-Движокъ: the game's own engine core.
/// Runs simulation subsystems on a fixed timestep, so the world behaves
/// deterministically regardless of the device's frame rate. Rendering is
/// delegated to Metal (via SceneKit); everything above the renderer —
/// time, weather, history, persistence, characters — is ours.
final class RomanovEngine {
    static let version = "0.2.0"

    private(set) var systems: [EngineSystem] = []
    private let fixedStep: Float = 1.0 / 60.0
    private var accumulator: Float = 0

    func register(_ system: EngineSystem) {
        systems.append(system)
    }

    /// Fixed-timestep pump. Spikes are clamped so a hitch never causes a
    /// spiral of death.
    func update(frameDt: Float, context: EngineContext) {
        accumulator += min(frameDt, 0.25)
        while accumulator >= fixedStep {
            for s in systems {
                s.update(dt: fixedStep, context: context)
            }
            accumulator -= fixedStep
        }
    }
}
