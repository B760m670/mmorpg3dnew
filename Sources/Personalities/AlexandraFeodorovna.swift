import SceneKit
import UIKit

/// Александра Фёдоровна (25 мая 1872 — 17 июля 1918), урождённая принцесса
/// Алиса Гессен-Дармштадтская, внучка королевы Виктории.
/// Появляется в игре 10 октября 1894 года — в день реального приезда в Россию.
enum AlexandraFeodorovna {

    static let biography =
        "Алиса Виктория Елена Луиза Беатриса, принцесса Гессен-Дармштадтская, любимая внучка королевы Виктории. " +
        "Невеста, а с 14 ноября 1894 года — супруга Николая II. Приняла православие с именем Александра Фёдоровна. " +
        "Красавица с золотисто-рыжими волосами, застенчивая и глубоко верующая."

    static let persona = Persona(
        id: "alix",
        name: "Александра Ѳеодоровна",
        title: "Императрица",
        before: [
            "Ники, я приняла решение. Я приму православие — ради тебя и ради России.",
            "Мне страшно в этой огромной стране, но рядом с тобой я ничего не боюсь."
        ],
        after: [
            "Мы обвенчались в скорбные дни, но я счастлива быть рядом с тобой, Ники.",
            "Народ смотрит на нас. Будем же достойны его любви.",
            "Будь твёрд, мой милый. Помни — ты Самодержец, тебе не пристало уступать."
        ]
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.089
        face.headHeight = 0.115
        face.headDepth = 0.098
        face.browRidge = 0.0028
        face.eyeSocketDepth = 0.0050
        face.cheekbone = 0.0052
        face.noseRidge = 0.0072
        face.noseTip = 0.0090
        face.chin = 0.0062
        face.jawNarrowing = 0.28
        face.skinTone = UIColor(red: 0.93, green: 0.79, blue: 0.70, alpha: 1)
        face.eyeColor = UIColor(red: 0.42, green: 0.55, blue: 0.60, alpha: 1) // серо-голубые
        face.hairColor = UIColor(red: 0.52, green: 0.32, blue: 0.16, alpha: 1) // золотисто-рыжие
        face.femaleHair = true

        var body = BodySpec()
        body.overallScale = 0.97 // высокая для женщины той эпохи
        body.stoutness = 0.94
        body.isDress = true
        body.dressColor = UIColor(red: 0.89, green: 0.86, blue: 0.79, alpha: 1)
        body.collarColor = nil
        body.cuffColor = nil
        body.ladyHat = true
        body.ladyHatColor = UIColor(white: 0.93, alpha: 1)

        return HumanBody.make(face: face, body: body)
    }
}
