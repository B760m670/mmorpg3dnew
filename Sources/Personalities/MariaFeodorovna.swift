import SceneKit
import UIKit

/// Мария Фёдоровна (14 ноября 1847 — 13 октября 1928), урождённая принцесса
/// Дагмар Датская. Супруга Александра III, мать Николая II.
/// После 20 октября 1894 года носит траур.
enum MariaFeodorovna {

    static let biography =
        "Мария Фёдоровна, урождённая принцесса Дагмар Датская, супруга Александра III. " +
        "Маленькая, изящная, обаятельная — любимица петербургского света. Покровительница Российского общества Красного Креста " +
        "и учреждений ведомства императрицы Марии. После смерти мужа — вдовствующая императрица."

    static let persona = Persona(
        id: "maria",
        name: "Марія Ѳеодоровна",
        title: "Императрица",
        before: [
            "Ники, милый, ты слишком мягок. Государю нужна твёрдость, помни это.",
            "Отец твой нездоров. Осенью мы едем в Ливадию — крымский воздух должен помочь.",
            "Я пишу сестре Александре в Лондон. Вся Европа нынче — одна большая семья."
        ],
        after: [
            "Теперь ты Император, мой мальчик. Да поможет тебе Бог нести это бремя.",
            "Я ношу траур по твоему отцу и буду носить его до конца дней. Держись, Ники.",
            "Не спеши доверять министрам. Отец твой говорил: у России друзей нет."
        ]
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.088
        face.headHeight = 0.112
        face.headDepth = 0.096
        face.browRidge = 0.0030
        face.eyeSocketDepth = 0.0048
        face.cheekbone = 0.0058
        face.noseRidge = 0.0068
        face.noseTip = 0.0085
        face.chin = 0.0058
        face.jawNarrowing = 0.30
        face.skinTone = UIColor(red: 0.92, green: 0.78, blue: 0.68, alpha: 1)
        face.eyeColor = UIColor(red: 0.32, green: 0.26, blue: 0.20, alpha: 1) // тёмные датские глаза
        face.hairColor = UIColor(red: 0.18, green: 0.12, blue: 0.08, alpha: 1)
        face.femaleHair = true

        var body = BodySpec()
        body.overallScale = 0.90 // миниатюрная
        body.stoutness = 0.92
        body.isDress = true
        body.dressColor = UIColor(red: 0.13, green: 0.17, blue: 0.30, alpha: 1)
        body.collarColor = nil
        body.cuffColor = nil
        body.ladyHat = true
        body.ladyHatColor = UIColor(red: 0.13, green: 0.17, blue: 0.30, alpha: 1)

        return HumanBody.make(face: face, body: body)
    }
}
