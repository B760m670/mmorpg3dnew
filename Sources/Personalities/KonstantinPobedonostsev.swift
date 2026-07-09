import SceneKit
import UIKit

/// Константин Петрович Победоносцев (21 мая 1827 — 10 марта 1907).
/// Обер-прокурор Святейшего Синода, наставник двух императоров.
enum KonstantinPobedonostsev {

    static let biography =
        "Константин Петрович Победоносцев, обер-прокурор Святейшего Синода с 1880 года. Правовед, преподавал " +
        "законоведение Александру III и Николаю II. Идеолог контрреформ, непримиримый противник парламентаризма. " +
        "Сухой, аскетичный старик в очках, которого за глаза звали «великим инквизитором»."

    static let persona = Persona(
        id: "pobedonostsev",
        name: "Константинъ Побѣдоносцевъ",
        title: "Оберъ-прокуроръ Синода",
        before: [
            "Парламенты — великая ложь нашего времени. Самодержавие — единственная форма правления, пригодная для России.",
            "Я преподавал право Вашему батюшке и Вам. Храните заветы старины, Ваше Высочество.",
            "Печать развращает умы. За газетами нужен глаз да глаз."
        ],
        after: [
            "Не слушайте тех, кто шепчет о конституции, Ваше Величество. Это погубит Россию.",
            "Земцы снова просят «участия в управлении». Назовите вещи своими именами: это бессмысленные мечтания.",
            "Россия сильна верой и самодержавием. Ослабнет одно — рухнет и другое."
        ]
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.091
        face.headHeight = 0.120
        face.headDepth = 0.100
        face.browRidge = 0.0068
        face.eyeSocketDepth = 0.0072 // запавшие глаза
        face.cheekbone = 0.0068      // худое лицо
        face.noseRidge = 0.0088
        face.noseTip = 0.0095
        face.chin = 0.0055
        face.jawNarrowing = 0.30
        face.skinTone = UIColor(red: 0.87, green: 0.73, blue: 0.62, alpha: 1)
        face.eyeColor = UIColor(red: 0.30, green: 0.32, blue: 0.34, alpha: 1)
        face.hairColor = UIColor(white: 0.72, alpha: 1)
        face.beardColor = UIColor(white: 0.75, alpha: 1)
        face.bald = true
        face.hasSideWhiskers = true
        face.glasses = true

        var body = BodySpec()
        body.overallScale = 0.95
        body.stoutness = 0.90 // сухой, аскетичный
        body.tunicColor = UIColor(white: 0.09, alpha: 1) // чёрный сюртук
        body.collarColor = nil
        body.cuffColor = nil
        body.epaulettes = false
        body.medals = false
        body.beltAndBuckle = false
        body.highBoots = false
        body.peakedCap = false

        return HumanBody.make(face: face, body: body)
    }
}
