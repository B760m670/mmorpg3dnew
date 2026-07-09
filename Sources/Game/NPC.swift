import SceneKit

/// A historical figure living in the world: wanders near a home point,
/// stops and faces the player when approached.
final class NPC {
    let character: GameCharacter
    let personaId: String
    let home: SCNVector3
    let wanderRadius: Float

    private var target: SCNVector3?
    private var pauseTime: Float = 0
    private var rnd: SeededRandom

    var position: SCNVector3 { return character.root.position }

    init(character: GameCharacter, personaId: String, home: SCNVector3, wanderRadius: Float, seed: UInt64) {
        self.character = character
        self.personaId = personaId
        self.home = home
        self.wanderRadius = wanderRadius
        self.rnd = SeededRandom(seed: seed)
        character.root.position = home
    }

    func update(dt: Float, playerPos: SCNVector3) {
        let toPlayer = SCNVector3(playerPos.x - position.x, 0, playerPos.z - position.z)
        let playerDist = toPlayer.length

        // face the player when they come close
        if playerDist < 4.0 {
            if playerDist > 0.01 {
                let yaw = atan2f(toPlayer.x, toPlayer.z)
                character.root.eulerAngles.y = approachAngle(character.root.eulerAngles.y, yaw, dt * 6)
            }
            character.updateWalk(dt: dt, speed: 0)
            target = nil
            pauseTime = Float(rnd.range(2, 5))
            return
        }

        guard wanderRadius > 0.1 else {
            character.updateWalk(dt: dt, speed: 0)
            return
        }

        if let t = target {
            let d = SCNVector3(t.x - position.x, 0, t.z - position.z)
            let dist = d.length
            if dist < 0.4 {
                target = nil
                pauseTime = Float(rnd.range(4, 10))
                character.updateWalk(dt: dt, speed: 0)
            } else {
                let speed: Float = 0.85
                let yaw = atan2f(d.x, d.z)
                character.root.eulerAngles.y = approachAngle(character.root.eulerAngles.y, yaw, dt * 4)
                character.root.position.x += d.x / dist * speed * dt
                character.root.position.z += d.z / dist * speed * dt
                character.updateWalk(dt: dt, speed: speed)
            }
        } else {
            pauseTime -= dt
            character.updateWalk(dt: dt, speed: 0)
            if pauseTime <= 0 {
                let a = Float(rnd.range(0, Double.pi * 2))
                let r = Float(rnd.range(0.3, 1.0)) * wanderRadius
                target = SCNVector3(home.x + sinf(a) * r, 0, home.z + cosf(a) * r)
            }
        }
    }
}
