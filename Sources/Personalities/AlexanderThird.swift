import SceneKit
import UIKit

/// Александр III Александрович (26 февраля 1845 — 20 октября 1894).
/// «Миротворец». Богатырского сложения, с окладистой бородой.
/// В игре присутствует до своей исторической кончины 20 октября 1894 года.
enum AlexanderThird {

    static let biography =
        "Александр III, Император Всероссийский с 1881 года. За тринадцать лет царствования Россия не вела ни одной войны, " +
        "за что государь получил прозвание Миротворца. Человек огромной физической силы — гнул подковы и удерживал на плечах " +
        "крышу вагона при крушении поезда в Борках. Скончался от нефрита в Ливадии 20 октября 1894 года."

    static let persona = Persona(
        id: "alexander3",
        name: "Александръ III",
        title: "Императоръ Всероссійскій",
        before: [
            "Николай, запомни: у России есть только два верных союзника — её армия и её флот.",
            "Я нездоров, сын мой. Врачи советуют Крым… Но дела государственные не ждут.",
            "Слушай Победоносцева, но решать учись сам. Самодержец отвечает лишь перед Богом.",
            "Твоя Алиса — достойная девица. Я дал согласие на помолвку. Береги её.",
            "Тринадцать лет я хранил мир. Ни одной войны. Пусть Европа подождёт, пока русский царь удит рыбу."
        ],
        after: []
    )

    static func makeCharacter() -> GameCharacter {
        var face = FaceSpec()
        face.headWidth = 0.102
        face.headHeight = 0.120
        face.headDepth = 0.108
        face.browRidge = 0.0072
        face.noseTip = 0.0120
        face.chin = 0.0060
        face.jawNarrowing = 0.10 // квадратная, мощная челюсть
        face.skinTone = UIColor(red: 0.89, green: 0.72, blue: 0.60, alpha: 1)
        face.eyeColor = UIColor(red: 0.40, green: 0.50, blue: 0.58, alpha: 1)
        face.hairColor = UIColor(red: 0.28, green: 0.21, blue: 0.14, alpha: 1)
        face.beardColor = UIColor(red: 0.33, green: 0.25, blue: 0.16, alpha: 1)
        face.hasBigBeard = true
        face.hasMustache = true

        var body = BodySpec()
        body.overallScale = 1.10 // 193 см, богатырь
        body.stoutness = 1.22
        body.tunicColor = UIColor(red: 0.11, green: 0.14, blue: 0.20, alpha: 1)
        body.collarColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.cuffColor = UIColor(red: 0.64, green: 0.10, blue: 0.10, alpha: 1)
        body.epaulettes = true
        body.medals = true
        body.beltAndBuckle = true
        body.highBoots = true
        body.peakedCap = true
        body.capColor = UIColor(red: 0.10, green: 0.13, blue: 0.18, alpha: 1)

        return HumanBody.make(face: face, body: body)
    }
}
