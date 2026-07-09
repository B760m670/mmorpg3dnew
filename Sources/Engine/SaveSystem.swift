import Foundation

/// A snapshot of the player's story: the game autosaves every in-game day,
/// so a long historical campaign is never lost.
struct GameSave: Codable {
    var year: Int
    var month: Int
    var day: Int
    var hour: Double
    var accession: Bool
    var metPersonas: [String]
    var journal: [String]
    var playerX: Float
    var playerZ: Float
    var speedMultiplier: Double
}

enum SaveSystem {

    private static var url: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("empire1894-save.json")
    }

    static func save(_ s: GameSave) {
        if let data = try? JSONEncoder().encode(s) {
            try? data.write(to: url, options: .atomic)
        }
    }

    static func load() -> GameSave? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(GameSave.self, from: data)
    }

    static func wipe() {
        try? FileManager.default.removeItem(at: url)
    }
}
