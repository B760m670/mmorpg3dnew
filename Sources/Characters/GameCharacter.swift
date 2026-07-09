import SceneKit

/// A living character: procedural body with an animatable joint rig.
/// Legacy (simple) characters fill only the four limb pivots; the realistic
/// pipeline (HumanBody) also provides knees, elbows, pelvis and head.
final class GameCharacter {
    let root = SCNNode()

    // shoulder / hip pivots
    var leftArm: SCNNode?
    var rightArm: SCNNode?
    var leftLeg: SCNNode?
    var rightLeg: SCNNode?

    // extended rig (realistic pipeline)
    var leftElbow: SCNNode?
    var rightElbow: SCNNode?
    var leftKnee: SCNNode?
    var rightKnee: SCNNode?
    var pelvis: SCNNode?
    var basePelvisY: Float = 0
    var headNode: SCNNode?

    /// Materials that can be re-tinted at runtime (e.g. mourning dress).
    var clothMaterials: [SCNMaterial] = []

    private var walkPhase: Float = 0
    private var idleTime: Float = 0

    /// Procedural gait. speed in m/s; 0 relaxes into a breathing idle.
    func updateWalk(dt: Float, speed: Float) {
        if speed > 0.05 {
            walkPhase += dt * (3.0 + speed * 2.2)
            let amp = min(speed / 3.0, 1.0) * 0.6
            let s = sinf(walkPhase)

            leftArm?.eulerAngles.x = s * amp * 0.75
            rightArm?.eulerAngles.x = -s * amp * 0.75
            leftLeg?.eulerAngles.x = -s * amp
            rightLeg?.eulerAngles.x = s * amp

            // knees flex on the swing-through, elbows stay slightly bent
            leftKnee?.eulerAngles.x = -MeshBuilder.bump(sinf(walkPhase - 0.9), center: 1, width: 0.8) * amp * 1.15
            rightKnee?.eulerAngles.x = -MeshBuilder.bump(sinf(walkPhase - 0.9 + Float.pi), center: 1, width: 0.8) * amp * 1.15
            leftElbow?.eulerAngles.x = 0.25 + max(0, -s) * amp * 0.45
            rightElbow?.eulerAngles.x = 0.25 + max(0, s) * amp * 0.45

            if let p = pelvis {
                p.position.y = basePelvisY + fabsf(sinf(walkPhase)) * 0.028
                p.eulerAngles.z = s * 0.035
                p.eulerAngles.x = 0.04
            }
            headNode?.eulerAngles.x = -0.04
        } else {
            idleTime += dt
            leftArm?.eulerAngles.x *= 0.85
            rightArm?.eulerAngles.x *= 0.85
            leftLeg?.eulerAngles.x *= 0.85
            rightLeg?.eulerAngles.x *= 0.85
            leftKnee?.eulerAngles.x *= 0.85
            rightKnee?.eulerAngles.x *= 0.85

            // quiet breathing and a natural resting elbow bend
            let breath = sinf(idleTime * 1.7) * 0.5 + 0.5
            leftElbow?.eulerAngles.x = 0.16 + breath * 0.03
            rightElbow?.eulerAngles.x = 0.16 + breath * 0.03
            if let p = pelvis {
                p.position.y = basePelvisY + breath * 0.004
                p.eulerAngles.z *= 0.9
                p.eulerAngles.x *= 0.9
            }
            headNode?.eulerAngles.x = sinf(idleTime * 0.6) * 0.02
        }
    }
}
