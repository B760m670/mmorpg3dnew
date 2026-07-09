import SceneKit
import UIKit

/// Сергей Юльевич Витте (17 июня 1849 — 28 февраля 1915).
/// Министр финансов, архитектор индустриализации и золотого рубля.
enum SergeiWitte {

    static let biography =
        "Сергей Юльевич Витте, министр финансов с 1892 года. Строитель Великого Сибирского пути, автор денежной реформы " +
        "1897 года, обеспечившей рубль золотом, и винной монополии. Человек громадного роста и такой же энергии; " +
        "говорил с южным акцентом и не стеснялся спорить с самим государем."

    static let persona = Persona(
        id: "witte",
        name: "Сергѣй Витте",
        title: "Министръ финансовъ",
        before: [
            "Ваше Императорское Высочество! Великий Сибирский путь — вот будущее России. Рельсы уже идут через тайгу.",
            "Финансы империи требуют твёрдой валюты. Я готовлю реформу: рубль будет обеспечен золотом.",
            "Промышленность — вот истинная сила державы. Уголь, железо, мануфактуры!"
        ],
        after: [
            "Ваше Величество, промышленность растёт небывалыми темпами. Иностранный капитал идёт в Россию рекой.",
            "Золотой рубль сделает казну несокрушимой, а винная монополия — полной.",
            "Осмелюсь доложить: за десять лет мы удвоим выплавку чугуна. Россия догонит Европу."
        ]
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.099
        face.headHeight = 0.121
        face.headDepth = 0.106
        face.browRidge = 0.0064
        face.noseRidge = 0.0095
        face.noseTip = 0.0125 // крупный нос
        face.chin = 0.0050
        face.jawNarrowing = 0.14
        face.skinTone = UIColor(red: 0.90, green: 0.74, blue: 0.62, alpha: 1)
        face.eyeColor = UIColor(red: 0.34, green: 0.30, blue: 0.24, alpha: 1)
        face.hairColor = UIColor(red: 0.42, green: 0.38, blue: 0.34, alpha: 1) // седеющий
        face.beardColor = UIColor(red: 0.46, green: 0.42, blue: 0.38, alpha: 1)
        face.hasBigBeard = true
        face.hasMustache = true

        var body = BodySpec()
        body.overallScale = 1.10 // очень высокий
        body.stoutness = 1.15
        body.tunicColor = UIColor(white: 0.14, alpha: 1) // штатский сюртук
        body.collarColor = nil
        body.cuffColor = nil
        body.epaulettes = false
        body.medals = true
        body.beltAndBuckle = false
        body.highBoots = false
        body.peakedCap = false

        return HumanBody.make(face: face, body: body)
    }
}
