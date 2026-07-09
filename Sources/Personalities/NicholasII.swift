import SceneKit
import UIKit

/// Николай II Александрович (6 мая 1868 — 17 июля 1918).
/// Игровой персонаж. Внешность по портретам 1890-х: рост около 170 см,
/// аккуратная короткая борода и усы, серо-голубые глаза, тёмно-русые волосы,
/// китель Лейб-гвардии Преображенского полка с красным воротником.
enum NicholasII {

    static let biography =
        "Николай Александрович Романов, старший сын Александра III. Родился 6 мая 1868 года в Царском Селе. " +
        "Получил военное и юридическое образование, совершил кругосветное путешествие 1890–1891 годов. " +
        "Полковник Лейб-гвардии Преображенского полка. С 20 октября 1894 года — Император Всероссийский."

    static let persona = Persona(
        id: "nicholas",
        name: "Николай Александровичъ",
        title: "Цесаревичъ",
        before: [],
        after: []
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.094
        face.headHeight = 0.118
        face.headDepth = 0.102
        face.browRidge = 0.0058
        face.noseRidge = 0.0090
        face.noseTip = 0.0105
        face.chin = 0.0075
        face.jawNarrowing = 0.24
        face.skinTone = UIColor(red: 0.90, green: 0.75, blue: 0.64, alpha: 1)
        face.eyeColor = UIColor(red: 0.44, green: 0.56, blue: 0.64, alpha: 1) // серо-голубые
        face.hairColor = UIColor(red: 0.30, green: 0.21, blue: 0.12, alpha: 1)
        face.beardColor = UIColor(red: 0.34, green: 0.23, blue: 0.13, alpha: 1)
        face.hasShortBeard = true
        face.hasMustache = true

        var body = BodySpec()
        body.overallScale = 0.97 // император был невысок
        body.stoutness = 0.98
        body.tunicColor = UIColor(red: 0.13, green: 0.20, blue: 0.15, alpha: 1) // преображенский тёмно-зелёный
        body.collarColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.cuffColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.epaulettes = true
        body.medals = true
        body.beltAndBuckle = true
        body.highBoots = true
        body.peakedCap = true
        body.capColor = UIColor(red: 0.11, green: 0.17, blue: 0.13, alpha: 1)
        body.capBandColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)

        // Скульптурная голова из облачного Blender-конвейера
        // (MPFB2/MakeHuman -> морфы лица -> запечённая кожа -> OBJ).
        // При отсутствии модели в бандле игра откатывается на процедурную голову.
        let sculptedHead = HeadLoader.load(named: "nicholas_head",
                                           targetHeight: 0.295,
                                           skinTexture: "nicholas_skin.png",
                                           eyeTexture: "nicholas_eyes.png")

        return HumanBody.make(face: face, body: body, headOverride: sculptedHead)
    }
}
