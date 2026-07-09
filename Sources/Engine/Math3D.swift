import SceneKit

extension SCNVector3 {
    static func + (l: SCNVector3, r: SCNVector3) -> SCNVector3 {
        return SCNVector3(l.x + r.x, l.y + r.y, l.z + r.z)
    }
    static func - (l: SCNVector3, r: SCNVector3) -> SCNVector3 {
        return SCNVector3(l.x - r.x, l.y - r.y, l.z - r.z)
    }
    static func * (v: SCNVector3, s: Float) -> SCNVector3 {
        return SCNVector3(v.x * s, v.y * s, v.z * s)
    }
    var length: Float {
        return sqrtf(x * x + y * y + z * z)
    }
}

func lerpf(_ a: Float, _ b: Float, _ t: Float) -> Float {
    return a + (b - a) * t
}

/// Move an angle toward a target by at most maxDelta, taking the shortest path.
func approachAngle(_ current: Float, _ target: Float, _ maxDelta: Float) -> Float {
    var d = fmodf(target - current, 2 * Float.pi)
    if d > Float.pi { d -= 2 * Float.pi }
    if d < -Float.pi { d += 2 * Float.pi }
    return current + max(-maxDelta, min(maxDelta, d))
}

/// Axis-aligned obstacle in the XZ plane.
struct Collider {
    let minX: Float
    let maxX: Float
    let minZ: Float
    let maxZ: Float

    func contains(x: Float, z: Float, radius: Float) -> Bool {
        return x > minX - radius && x < maxX + radius
            && z > minZ - radius && z < maxZ + radius
    }
}

/// Deterministic pseudo-random generator so procedural textures/placement
/// look the same on every launch.
struct SeededRandom {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed &* 2862933555777941757 &+ 3037000493
    }

    mutating func next() -> Double {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        return Double((state >> 33) & 0x7FFFFFFF) / Double(0x7FFFFFFF)
    }

    mutating func range(_ lo: Double, _ hi: Double) -> Double {
        return lo + next() * (hi - lo)
    }
}
