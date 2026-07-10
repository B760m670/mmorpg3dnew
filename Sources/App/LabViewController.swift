import UIKit
import SceneKit

/// Лаборатория персонажей: студийное пространство, в котором персонаж
/// рассматривается со всех сторон, приближается щипком и переодевается.
/// Никаких зданий и погоды — только движок, свет и модель.
final class LabViewController: UIViewController {

    private var scnView: SCNView!
    private let scene = SCNScene()
    private let engine = RomanovEngine()
    private let labClock = HistoryClock()

    // персонаж: два варианта из Blender-конвейера
    private let characterRoot = SCNNode()
    private var uniformChar: GameCharacter?
    private var bodyChar: GameCharacter?
    private var showUniform = true
    private var characterYaw: Float = Float.pi
    private var turntable = false

    // камера
    private let rigNode = SCNNode()
    private let yawNode = SCNNode()
    private let pitchNode = SCNNode()
    private let cameraNode = SCNNode()
    private var camYaw: Float = Float.pi
    private var camPitch: Float = 0.12
    private var boom: Float = 3.2

    private var displayLink: CADisplayLink?
    private var lastTimestamp: CFTimeInterval = 0

    // UI
    private let joystick = VirtualJoystick(frame: .zero)
    private let titleLabel = UILabel()
    private let subtitleLabel = UILabel()
    private let outfitButton = UIButton(type: .system)
    private let turntableButton = UIButton(type: .system)
    private let hintLabel = UILabel()

    override var prefersStatusBarHidden: Bool { return true }
    override var prefersHomeIndicatorAutoHidden: Bool { return true }

    private func serifFont(_ size: CGFloat, bold: Bool = false) -> UIFont {
        let name = bold ? "Georgia-Bold" : "Georgia"
        return UIFont(name: name, size: size) ?? UIFont.systemFont(ofSize: size, weight: bold ? .bold : .regular)
    }

    override func viewDidLoad() {
        super.viewDidLoad()

        scnView = SCNView(frame: view.bounds)
        scnView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        scnView.scene = scene
        scnView.isPlaying = true
        scnView.rendersContinuously = true
        scnView.preferredFramesPerSecond = 60
        scnView.antialiasingMode = .multisampling4X
        view.addSubview(scnView)

        setupStudio()
        setupCharacters()
        setupCamera()
        setupUI()

        let pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.maximumNumberOfTouches = 1
        scnView.addGestureRecognizer(pan)
        let pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:)))
        scnView.addGestureRecognizer(pinch)

        let link = CADisplayLink(target: self, selector: #selector(step(_:)))
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    // MARK: - Студия

    private func makeGradient() -> UIImage {
        return Textures.image(512) { ctx, s in
            let colors = [UIColor(red: 0.16, green: 0.17, blue: 0.20, alpha: 1).cgColor,
                          UIColor(red: 0.32, green: 0.34, blue: 0.38, alpha: 1).cgColor] as CFArray
            let space = CGColorSpaceCreateDeviceRGB()
            if let g = CGGradient(colorsSpace: space, colors: colors, locations: [0, 1]) {
                ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: 0),
                                       end: CGPoint(x: 0, y: s), options: [])
            }
        }
    }

    private func setupStudio() {
        scene.background.contents = makeGradient()

        // подиум-пол
        let floorGeo = SCNCylinder(radius: 40, height: 0.1)
        let floorMat = SCNMaterial()
        floorMat.diffuse.contents = UIColor(red: 0.42, green: 0.43, blue: 0.45, alpha: 1)
        floorMat.lightingModel = .blinn
        floorMat.specular.contents = UIColor(white: 0.2, alpha: 1)
        floorGeo.materials = [floorMat]
        let floor = SCNNode(geometry: floorGeo)
        floor.position = SCNVector3(0, -0.05, 0)
        scene.rootNode.addChildNode(floor)

        // трёхточечный студийный свет
        let key = SCNLight()
        key.type = .directional
        key.intensity = 950
        key.color = UIColor(red: 1.0, green: 0.97, blue: 0.92, alpha: 1)
        key.castsShadow = true
        key.shadowMapSize = CGSize(width: 2048, height: 2048)
        key.shadowRadius = 6
        key.shadowColor = UIColor(white: 0, alpha: 0.5)
        let keyNode = SCNNode()
        keyNode.light = key
        keyNode.eulerAngles = SCNVector3(-0.9, -0.6, 0)
        scene.rootNode.addChildNode(keyNode)

        let fill = SCNLight()
        fill.type = .directional
        fill.intensity = 320
        fill.color = UIColor(red: 0.85, green: 0.9, blue: 1.0, alpha: 1)
        let fillNode = SCNNode()
        fillNode.light = fill
        fillNode.eulerAngles = SCNVector3(-0.4, 0.9, 0)
        scene.rootNode.addChildNode(fillNode)

        let rim = SCNLight()
        rim.type = .directional
        rim.intensity = 420
        rim.color = UIColor(red: 0.8, green: 0.87, blue: 1.0, alpha: 1)
        let rimNode = SCNNode()
        rimNode.light = rim
        rimNode.eulerAngles = SCNVector3(-0.5, Float.pi - 0.4, 0)
        scene.rootNode.addChildNode(rimNode)

        let ambient = SCNLight()
        ambient.type = .ambient
        ambient.intensity = 380
        ambient.color = UIColor(red: 0.6, green: 0.62, blue: 0.68, alpha: 1)
        let ambientNode = SCNNode()
        ambientNode.light = ambient
        scene.rootNode.addChildNode(ambientNode)
    }

    private func setupCharacters() {
        scene.rootNode.addChildNode(characterRoot)
        characterRoot.eulerAngles.y = characterYaw

        uniformChar = SegmentedCharacter.make(objName: "nicholas_uniform")
        bodyChar = SegmentedCharacter.make(objName: "nicholas_body")

        if let u = uniformChar {
            characterRoot.addChildNode(u.root)
        }
        if let b = bodyChar {
            b.root.isHidden = true
            characterRoot.addChildNode(b.root)
        }
    }

    private func setupCamera() {
        rigNode.position = SCNVector3(0, 1.05, 0)
        scene.rootNode.addChildNode(rigNode)
        rigNode.addChildNode(yawNode)
        yawNode.addChildNode(pitchNode)

        let camera = SCNCamera()
        camera.fieldOfView = 55
        camera.zNear = 0.05
        camera.zFar = 200
        cameraNode.camera = camera
        cameraNode.position = SCNVector3(0, 0, -boom)
        let lookAt = SCNLookAtConstraint(target: rigNode)
        lookAt.isGimbalLockEnabled = true
        cameraNode.constraints = [lookAt]
        pitchNode.addChildNode(cameraNode)

        yawNode.eulerAngles.y = camYaw
        pitchNode.eulerAngles.x = camPitch
    }

    // MARK: - UI

    private func styleButton(_ b: UIButton, _ title: String) {
        b.setTitle(title, for: .normal)
        b.setTitleColor(UIColor(red: 0.95, green: 0.88, blue: 0.7, alpha: 1), for: .normal)
        b.titleLabel?.font = serifFont(17, bold: true)
        b.backgroundColor = UIColor(red: 0.08, green: 0.07, blue: 0.06, alpha: 0.75)
        b.layer.cornerRadius = 10
        b.layer.borderWidth = 1
        b.layer.borderColor = UIColor(red: 0.85, green: 0.68, blue: 0.2, alpha: 0.6).cgColor
    }

    private func setupUI() {
        titleLabel.font = serifFont(22, bold: true)
        titleLabel.textColor = UIColor(red: 0.97, green: 0.93, blue: 0.82, alpha: 1)
        titleLabel.text = "ЛАБОРАТОРІЯ ПЕРСОНАЖЕЙ"
        titleLabel.layer.shadowColor = UIColor.black.cgColor
        titleLabel.layer.shadowOpacity = 0.8
        titleLabel.layer.shadowRadius = 3
        view.addSubview(titleLabel)

        subtitleLabel.font = serifFont(15)
        subtitleLabel.textColor = UIColor(white: 0.85, alpha: 1)
        subtitleLabel.text = "Николай II • анатомическая модель (Blender/MakeHuman)"
        view.addSubview(subtitleLabel)

        styleButton(outfitButton, "Тѣло")
        outfitButton.addTarget(self, action: #selector(toggleOutfit), for: .touchUpInside)
        view.addSubview(outfitButton)

        styleButton(turntableButton, "⟳ Поворотъ")
        turntableButton.addTarget(self, action: #selector(toggleTurntable), for: .touchUpInside)
        view.addSubview(turntableButton)

        hintLabel.font = serifFont(13)
        hintLabel.textColor = UIColor(white: 0.75, alpha: 1)
        hintLabel.text = "джойстикъ — ходьба • свайпъ — камера • щипокъ — приближеніе"
        hintLabel.textAlignment = .right
        view.addSubview(hintLabel)

        view.addSubview(joystick)

        if uniformChar == nil && bodyChar == nil {
            subtitleLabel.text = "Модель не загрузилась — \(SegmentedCharacter.diagnostics())"
            subtitleLabel.textColor = UIColor(red: 1, green: 0.5, blue: 0.4, alpha: 1)
            subtitleLabel.numberOfLines = 2
        }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let w = view.bounds.width
        let h = view.bounds.height
        let safe = view.safeAreaInsets
        titleLabel.frame = CGRect(x: safe.left + 20, y: 14, width: 520, height: 28)
        subtitleLabel.frame = CGRect(x: safe.left + 20, y: 42, width: 560, height: 20)
        outfitButton.frame = CGRect(x: w - safe.right - 150, y: 14, width: 130, height: 42)
        turntableButton.frame = CGRect(x: w - safe.right - 310, y: 14, width: 150, height: 42)
        joystick.frame = CGRect(x: safe.left + 26, y: h - 216, width: 190, height: 190)
        hintLabel.frame = CGRect(x: w - safe.right - 480, y: h - 34, width: 460, height: 20)
    }

    // MARK: - Действия

    @objc private func toggleOutfit() {
        showUniform.toggle()
        uniformChar?.root.isHidden = !showUniform
        bodyChar?.root.isHidden = showUniform
        outfitButton.setTitle(showUniform ? "Тѣло" : "Мундиръ", for: .normal)
    }

    @objc private func toggleTurntable() {
        turntable.toggle()
    }

    @objc private func handlePan(_ g: UIPanGestureRecognizer) {
        let t = g.translation(in: view)
        camYaw -= Float(t.x) * 0.006
        camPitch = max(-0.15, min(1.15, camPitch - Float(t.y) * 0.004))
        g.setTranslation(.zero, in: view)
        yawNode.eulerAngles.y = camYaw
        pitchNode.eulerAngles.x = camPitch
    }

    @objc private func handlePinch(_ g: UIPinchGestureRecognizer) {
        boom = max(0.9, min(9.0, boom / Float(g.scale)))
        g.scale = 1.0
        cameraNode.position = SCNVector3(0, 0, -boom)
    }

    // MARK: - Игровой цикл

    @objc private func step(_ link: CADisplayLink) {
        var dt = Float(link.timestamp - lastTimestamp)
        lastTimestamp = link.timestamp
        if dt <= 0 || dt > 0.1 { dt = 1.0 / 60.0 }

        let active = showUniform ? uniformChar : bodyChar

        // движение по студии
        let v = joystick.vector
        let mag = Float(min(1.0, sqrt(v.x * v.x + v.y * v.y)))
        if mag > 0.08 {
            let fx = sinf(camYaw), fz = cosf(camYaw)
            let rx = -cosf(camYaw), rz = sinf(camYaw)
            var dx = fx * Float(v.y) + rx * Float(v.x)
            var dz = fz * Float(v.y) + rz * Float(v.x)
            let len = sqrtf(dx * dx + dz * dz)
            if len > 0.001 { dx /= len; dz /= len }
            let speed = 1.6 * mag

            characterYaw = approachAngle(characterYaw, atan2f(dx, dz), dt * 8)
            characterRoot.eulerAngles.y = characterYaw
            var pos = characterRoot.position
            pos.x = max(-30, min(30, pos.x + dx * speed * dt))
            pos.z = max(-30, min(30, pos.z + dz * speed * dt))
            characterRoot.position = pos
            active?.updateWalk(dt: dt, speed: speed)
        } else {
            active?.updateWalk(dt: dt, speed: 0)
            if turntable {
                characterYaw += dt * 0.5
                characterRoot.eulerAngles.y = characterYaw
            }
        }

        // камера следует за персонажем
        let target = SCNVector3(characterRoot.position.x, 1.05, characterRoot.position.z)
        let k = min(1.0, dt * 8)
        rigNode.position = SCNVector3(lerpf(rigNode.position.x, target.x, k),
                                      lerpf(rigNode.position.y, target.y, k),
                                      lerpf(rigNode.position.z, target.z, k))

        engine.update(frameDt: dt, context: EngineContext(scene: scene, clock: labClock,
                                                          playerPosition: characterRoot.position))
    }
}
