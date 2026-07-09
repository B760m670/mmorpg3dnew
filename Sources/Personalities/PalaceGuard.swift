import SceneKit
import UIKit

/// Часовой Лейб-гвардии Преображенского полка у Зимнего дворца.
enum PalaceGuard {

    static let biography =
        "Лейб-гвардии Преображенский полк — старейший полк русской гвардии, основанный Петром Великим в 1691 году. " +
        "В его рядах служили все российские императоры; полковником полка был и цесаревич Николай Александрович."

    static let persona = Persona(
        id: "guard",
        name: "Лейбъ-гвардеецъ",
        title: "Преображенскій полкъ",
        before: [
            "Здравія желаю, Ваше Императорское Высочество!",
            "Пост у Зимняго дворца сдан исправно!"
        ],
        after: [
            "Здравія желаю, Ваше Императорское Величество!",
            "Рады стараться, Ваше Величество!"
        ]
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.096
        face.browRidge = 0.0060
        face.jawNarrowing = 0.18
        face.skinTone = UIColor(red: 0.89, green: 0.73, blue: 0.61, alpha: 1)
        face.eyeColor = UIColor(red: 0.35, green: 0.32, blue: 0.26, alpha: 1)
        face.hairColor = UIColor(red: 0.24, green: 0.17, blue: 0.10, alpha: 1)
        face.hasMustache = true

        var body = BodySpec()
        body.overallScale = 1.06 // в гвардию брали рослых
        body.stoutness = 1.05
        body.tunicColor = UIColor(red: 0.13, green: 0.20, blue: 0.15, alpha: 1)
        body.collarColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.cuffColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.epaulettes = true
        body.beltAndBuckle = true
        body.highBoots = true
        body.peakedCap = true

        return HumanBody.make(face: face, body: body)
    }
}
