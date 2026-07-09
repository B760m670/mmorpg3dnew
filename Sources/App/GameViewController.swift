import UIKit
import SceneKit

final class GameViewController: UIViewController {

    // MARK: - Scene
    private var scnView: SCNView!
    private let scene = SCNScene()
    private var colliders: [Collider] = []

    private var player: GameCharacter!
    private var playerYaw: Float = Float.pi
    private var npcs: [NPC] = []
    private var mariaCharacter: GameCharacter?
    private var alexanderNPC: NPC?
    private var pendingAlexandra: GameCharacter?

    // camera rig: rig -> yaw -> pitch -> camera(with look-at)
    private let rigNode = SCNNode()
    private let yawNode = SCNNode()
    private let pitchNode = SCNNode()
    private let cameraNode = SCNNode()
    private var camYaw: Float = Float.pi
    private var camPitch: Float = 0.30

    private let sunNode = SCNNode()
    private let ambientNode = SCNNode()
    private var snowNode: SCNNode?

    // MARK: - Game state
    private let engine = RomanovEngine()
    private let clock = HistoryClock()
    private var loadedSave: GameSave?
    private var accession = false
    private var displayLink: CADisplayLink?
    private var lastTimestamp: CFTimeInterval = 0
    private var started = false
    private var journalEntries: [String] = []
    private var lineIndices: [String: Int] = [:]
    private var activeNPC: NPC?
    private var metPersonas: Set<String> = []
    private var lastShownDay = -1

    // MARK: - UI
    private let joystick = VirtualJoystick(frame: .zero)
    private let dateLabel = UILabel()
    private let titleLabel = UILabel()
    private let journalButton = UIButton(type: .system)
    private let speedButton = UIButton(type: .system)
    private let interactButton = UIButton(type: .system)
    private let bannerLabel = UILabel()
    private var bannerQueue: [String] = []
    private var bannerBusy = false

    private let dialoguePanel = UIView()
    private let dialogueName = UILabel()
    private let dialogueText = UILabel()
    private let journalPanel = UIView()
    private let journalTextView = UITextView()
    private let introPanel = UIView()

    private func serifFont(_ size: CGFloat, bold: Bool = false) -> UIFont {
        let name = bold ? "Georgia-Bold" : "Georgia"
        return UIFont(name: name, size: size) ?? UIFont.systemFont(ofSize: size, weight: bold ? .bold : .regular)
    }

    override var prefersStatusBarHidden: Bool { return true }
    override var prefersHomeIndicatorAutoHidden: Bool { return true }

    // MARK: - Setup

    override func viewDidLoad() {
        super.viewDidLoad()

        scnView = SCNView(frame: view.bounds)
        scnView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        scnView.scene = scene
        scnView.isPlaying = true
        scnView.rendersContinuously = true
        scnView.preferredFramesPerSecond = 60
        scnView.antialiasingMode = .multisampling2X
        scnView.backgroundColor = .black
        view.addSubview(scnView)

        colliders = WorldBuilder.build(into: scene)
        snowNode = scene.rootNode.childNode(withName: "snow", recursively: false)

        setupLights()
        setupPlayerAndCamera()
        setupNPCs()

        engine.register(WeatherSystem())
        loadedSave = SaveSystem.load()

        setupUI()

        if let save = loadedSave {
            applyRestoredState(save)
        }

        let pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.maximumNumberOfTouches = 1
        scnView.addGestureRecognizer(pan)

        let link = CADisplayLink(target: self, selector: #selector(step(_:)))
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    private func setupLights() {
        let sun = SCNLight()
        sun.type = .directional
        sun.castsShadow = true
        sun.shadowMapSize = CGSize(width: 1024, height: 1024)
        sun.shadowRadius = 4
        sun.shadowColor = UIColor(white: 0, alpha: 0.55)
        sun.color = UIColor(red: 1.0, green: 0.9, blue: 0.75, alpha: 1)
        sunNode.light = sun
        sunNode.eulerAngles = SCNVector3(-0.7, -0.7, 0)
        scene.rootNode.addChildNode(sunNode)

        let ambient = SCNLight()
        ambient.type = .ambient
        ambient.color = UIColor(red: 0.55, green: 0.6, blue: 0.7, alpha: 1)
        ambient.intensity = 500
        ambientNode.light = ambient
        scene.rootNode.addChildNode(ambientNode)
    }

    private func setupPlayerAndCamera() {
        player = NicholasII.makeCharacter()
        player.root.position = SCNVector3(0, 0, 18)
        player.root.eulerAngles.y = playerYaw
        scene.rootNode.addChildNode(player.root)

        rigNode.position = SCNVector3(0, 1.6, 18)
        scene.rootNode.addChildNode(rigNode)
        rigNode.addChildNode(yawNode)
        yawNode.addChildNode(pitchNode)

        let camera = SCNCamera()
        camera.fieldOfView = 62
        camera.zNear = 0.1
        camera.zFar = 600
        cameraNode.camera = camera
        cameraNode.position = SCNVector3(0, 0, -8)
        let lookAt = SCNLookAtConstraint(target: rigNode)
        lookAt.isGimbalLockEnabled = true
        cameraNode.constraints = [lookAt]
        pitchNode.addChildNode(cameraNode)

        yawNode.eulerAngles.y = camYaw
        pitchNode.eulerAngles.x = camPitch
    }

    private func addNPC(_ character: GameCharacter, _ personaId: String,
                        x: Float, z: Float, wander: Float, seed: UInt64) -> NPC {
        let npc = NPC(character: character, personaId: personaId,
                      home: SCNVector3(x, 0, z), wanderRadius: wander, seed: seed)
        scene.rootNode.addChildNode(character.root)
        npcs.append(npc)
        return npc
    }

    private func setupNPCs() {
        alexanderNPC = addNPC(AlexanderThird.makeCharacter(), "alexander3", x: -6, z: -40, wander: 5, seed: 11)
        let maria = MariaFeodorovna.makeCharacter()
        mariaCharacter = maria
        _ = addNPC(maria, "maria", x: -11, z: -38, wander: 4, seed: 22)
        _ = addNPC(SergeiWitte.makeCharacter(), "witte", x: -26, z: 8, wander: 7, seed: 33)
        _ = addNPC(KonstantinPobedonostsev.makeCharacter(), "pobedonostsev", x: 22, z: 20, wander: 6, seed: 44)
        _ = addNPC(PalaceGuard.makeCharacter(), "guard", x: -8, z: -50, wander: 0, seed: 55)
        _ = addNPC(PalaceGuard.makeCharacter(), "guard", x: 8, z: -50, wander: 0, seed: 66)
        // Alexandra arrives in Russia on 10 October 1894 (event "alix")
        pendingAlexandra = AlexandraFeodorovna.makeCharacter()
    }

    // MARK: - UI construction

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
        dateLabel.font = serifFont(20, bold: true)
        dateLabel.textColor = UIColor(red: 0.97, green: 0.93, blue: 0.82, alpha: 1)
        dateLabel.layer.shadowColor = UIColor.black.cgColor
        dateLabel.layer.shadowOpacity = 0.9
        dateLabel.layer.shadowRadius = 3
        dateLabel.layer.shadowOffset = CGSize(width: 0, height: 1)
        view.addSubview(dateLabel)

        titleLabel.font = serifFont(14)
        titleLabel.textColor = UIColor(red: 0.9, green: 0.85, blue: 0.7, alpha: 1)
        titleLabel.text = "Е.И.В. Цесаревичъ Николай Александровичъ"
        titleLabel.layer.shadowColor = UIColor.black.cgColor
        titleLabel.layer.shadowOpacity = 0.9
        titleLabel.layer.shadowRadius = 3
        view.addSubview(titleLabel)

        styleButton(journalButton, "📖 Дневникъ")
        journalButton.addTarget(self, action: #selector(toggleJournal), for: .touchUpInside)
        view.addSubview(journalButton)

        styleButton(speedButton, "⏩ ×1")
        speedButton.addTarget(self, action: #selector(toggleSpeed), for: .touchUpInside)
        view.addSubview(speedButton)

        styleButton(interactButton, "Говорить")
        interactButton.isHidden = true
        interactButton.addTarget(self, action: #selector(interact), for: .touchUpInside)
        view.addSubview(interactButton)

        bannerLabel.font = serifFont(18, bold: true)
        bannerLabel.textColor = UIColor(red: 0.97, green: 0.93, blue: 0.82, alpha: 1)
        bannerLabel.backgroundColor = UIColor(red: 0.1, green: 0.08, blue: 0.06, alpha: 0.85)
        bannerLabel.textAlignment = .center
        bannerLabel.numberOfLines = 2
        bannerLabel.layer.cornerRadius = 12
        bannerLabel.layer.masksToBounds = true
        bannerLabel.layer.borderWidth = 1
        bannerLabel.layer.borderColor = UIColor(red: 0.85, green: 0.68, blue: 0.2, alpha: 0.7).cgColor
        bannerLabel.alpha = 0
        view.addSubview(bannerLabel)

        // dialogue panel
        dialoguePanel.backgroundColor = UIColor(red: 0.07, green: 0.06, blue: 0.05, alpha: 0.88)
        dialoguePanel.layer.cornerRadius = 14
        dialoguePanel.layer.borderWidth = 1
        dialoguePanel.layer.borderColor = UIColor(red: 0.85, green: 0.68, blue: 0.2, alpha: 0.6).cgColor
        dialoguePanel.isHidden = true
        view.addSubview(dialoguePanel)

        dialogueName.font = serifFont(17, bold: true)
        dialogueName.textColor = UIColor(red: 0.95, green: 0.8, blue: 0.4, alpha: 1)
        dialoguePanel.addSubview(dialogueName)

        dialogueText.font = serifFont(16)
        dialogueText.textColor = UIColor(white: 0.95, alpha: 1)
        dialogueText.numberOfLines = 0
        dialoguePanel.addSubview(dialogueText)

        let dialogueTap = UITapGestureRecognizer(target: self, action: #selector(advanceDialogue))
        dialoguePanel.addGestureRecognizer(dialogueTap)

        // journal panel
        journalPanel.backgroundColor = UIColor(red: 0.06, green: 0.05, blue: 0.04, alpha: 0.94)
        journalPanel.isHidden = true
        view.addSubview(journalPanel)

        let journalTitle = UILabel()
        journalTitle.font = serifFont(24, bold: true)
        journalTitle.textColor = UIColor(red: 0.95, green: 0.8, blue: 0.4, alpha: 1)
        journalTitle.text = "Дневникъ событій"
        journalTitle.tag = 701
        journalPanel.addSubview(journalTitle)

        journalTextView.backgroundColor = .clear
        journalTextView.font = serifFont(16)
        journalTextView.textColor = UIColor(white: 0.92, alpha: 1)
        journalTextView.isEditable = false
        journalPanel.addSubview(journalTextView)

        let journalClose = UIButton(type: .system)
        styleButton(journalClose, "✕ Закрыть")
        journalClose.tag = 702
        journalClose.addTarget(self, action: #selector(toggleJournal), for: .touchUpInside)
        journalPanel.addSubview(journalClose)

        joystick.isHidden = true
        view.addSubview(joystick)

        setupIntro()
        journalEntries.append("1 января 1894 г. — Новый годъ\nСанкт-Петербург встречает 1894 год. Цесаревич Николай Александрович прогуливается по Дворцовой площади.")
    }

    private func setupIntro() {
        introPanel.backgroundColor = UIColor(red: 0.04, green: 0.03, blue: 0.03, alpha: 0.96)
        view.addSubview(introPanel)

        let title = UILabel()
        title.tag = 801
        title.font = serifFont(34, bold: true)
        title.textColor = UIColor(red: 0.95, green: 0.8, blue: 0.4, alpha: 1)
        title.text = "РОССІЙСКАЯ ИМПЕРІЯ"
        title.textAlignment = .center
        introPanel.addSubview(title)

        let subtitle = UILabel()
        subtitle.tag = 802
        subtitle.font = serifFont(18)
        subtitle.textColor = UIColor(white: 0.9, alpha: 1)
        subtitle.text = "С.-Петербургъ • Дворцовая площадь • 1 января 1894 года"
        subtitle.textAlignment = .center
        introPanel.addSubview(subtitle)

        let body = UILabel()
        body.tag = 803
        body.font = serifFont(15)
        body.textColor = UIColor(white: 0.8, alpha: 1)
        body.numberOfLines = 0
        body.textAlignment = .center
        body.text = "Вы — цесаревич Николай Александрович, наследник российского престола.\nВашему отцу, императору Александру III, нездоровится. Грядёт год, который изменит вашу судьбу и судьбу империи.\nВсе события игры подлинны и наступают в свои исторические даты (по старому стилю).\n\nЛевый джойстик — движение • правая половина экрана — камера\nПодходите к людям и говорите с ними • ⏩ ускоряет время"
        introPanel.addSubview(body)

        let start = UIButton(type: .system)
        start.tag = 804
        styleButton(start, loadedSave == nil ? "НАЧАТЬ" : "ПРОДОЛЖИТЬ")
        start.titleLabel?.font = serifFont(22, bold: true)
        start.addTarget(self, action: #selector(startGame), for: .touchUpInside)
        introPanel.addSubview(start)
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        let w = view.bounds.width
        let h = view.bounds.height
        let safe = view.safeAreaInsets

        dateLabel.frame = CGRect(x: safe.left + 20, y: 14, width: 420, height: 26)
        titleLabel.frame = CGRect(x: safe.left + 20, y: 40, width: 460, height: 20)
        journalButton.frame = CGRect(x: w - safe.right - 170, y: 14, width: 150, height: 42)
        speedButton.frame = CGRect(x: w - safe.right - 250, y: 14, width: 70, height: 42)
        interactButton.frame = CGRect(x: w - safe.right - 200, y: h - 120, width: 180, height: 52)
        joystick.frame = CGRect(x: safe.left + 26, y: h - 216, width: 190, height: 190)
        bannerLabel.frame = CGRect(x: w / 2 - 260, y: 70, width: 520, height: 58)

        let dpW = min(w - 240, 620)
        dialoguePanel.frame = CGRect(x: (w - dpW) / 2, y: h - 168, width: dpW, height: 140)
        dialogueName.frame = CGRect(x: 18, y: 10, width: dpW - 36, height: 24)
        dialogueText.frame = CGRect(x: 18, y: 38, width: dpW - 36, height: 92)

        journalPanel.frame = view.bounds
        journalPanel.viewWithTag(701)?.frame = CGRect(x: 40, y: 24, width: w - 80, height: 36)
        journalTextView.frame = CGRect(x: 40, y: 70, width: w - 80, height: h - 90)
        journalPanel.viewWithTag(702)?.frame = CGRect(x: w - 180, y: 22, width: 140, height: 42)

        introPanel.frame = view.bounds
        introPanel.viewWithTag(801)?.frame = CGRect(x: 20, y: h * 0.10, width: w - 40, height: 44)
        introPanel.viewWithTag(802)?.frame = CGRect(x: 20, y: h * 0.10 + 48, width: w - 40, height: 26)
        introPanel.viewWithTag(803)?.frame = CGRect(x: w * 0.14, y: h * 0.10 + 84, width: w * 0.72, height: h * 0.52)
        introPanel.viewWithTag(804)?.frame = CGRect(x: w / 2 - 110, y: h - 100, width: 220, height: 56)
    }

    // MARK: - Actions

    @objc private func startGame() {
        started = true
        clock.isRunning = true
        joystick.isHidden = false
        UIView.animate(withDuration: 0.6, animations: { self.introPanel.alpha = 0 }) { _ in
            self.introPanel.isHidden = true
        }
    }

    @objc private func toggleSpeed() {
        if clock.speedMultiplier > 1 {
            clock.speedMultiplier = 1
            speedButton.setTitle("⏩ ×1", for: .normal)
        } else {
            clock.speedMultiplier = 8
            speedButton.setTitle("⏩ ×8", for: .normal)
        }
    }

    @objc private func toggleJournal() {
        if journalPanel.isHidden {
            journalTextView.text = journalEntries.joined(separator: "\n\n────────────\n\n")
            journalPanel.isHidden = false
        } else {
            journalPanel.isHidden = true
        }
    }

    @objc private func handlePan(_ g: UIPanGestureRecognizer) {
        let t = g.translation(in: view)
        camYaw += Float(t.x) * 0.006
        camPitch = max(0.06, min(0.9, camPitch - Float(t.y) * 0.004))
        g.setTranslation(.zero, in: view)
        yawNode.eulerAngles.y = camYaw
        pitchNode.eulerAngles.x = camPitch
    }

    @objc private func interact() {
        guard let npc = activeNPC, let persona = GameData.personas[npc.personaId] else { return }
        dialogueName.text = "\(persona.name) — \(persona.title)"
        // first meeting adds the person's biography to the journal
        if !metPersonas.contains(persona.id) {
            metPersonas.insert(persona.id)
            if let bio = GameData.biographies[persona.id] {
                journalEntries.insert("\(persona.name)\n\(bio)", at: 0)
            }
        }
        showNextLine(for: persona)
        dialoguePanel.isHidden = false
        interactButton.isHidden = true
    }

    @objc private func advanceDialogue() {
        guard let npc = activeNPC, let persona = GameData.personas[npc.personaId] else {
            dialoguePanel.isHidden = true
            return
        }
        showNextLine(for: persona)
    }

    private func showNextLine(for persona: Persona) {
        let lines = accession && !persona.after.isEmpty ? persona.after : persona.before
        guard !lines.isEmpty else {
            dialoguePanel.isHidden = true
            return
        }
        let idx = lineIndices[persona.id] ?? 0
        if idx >= lines.count {
            lineIndices[persona.id] = 0
            dialoguePanel.isHidden = true
            return
        }
        dialogueText.text = "«\(lines[idx])»"
        lineIndices[persona.id] = idx + 1
    }

    // MARK: - Banner

    private func banner(_ text: String) {
        bannerQueue.append(text)
        showNextBanner()
    }

    private func showNextBanner() {
        guard !bannerBusy, !bannerQueue.isEmpty else { return }
        bannerBusy = true
        bannerLabel.text = bannerQueue.removeFirst()
        UIView.animate(withDuration: 0.4, animations: { self.bannerLabel.alpha = 1 }) { _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 4.5) {
                UIView.animate(withDuration: 0.6, animations: { self.bannerLabel.alpha = 0 }) { _ in
                    self.bannerBusy = false
                    self.showNextBanner()
                }
            }
        }
    }

    // MARK: - Historical events

    private func fire(_ e: HistoricalEvent) {
        let dateStr = "\(e.day) \(HistoryClock.monthNames[e.month - 1]) \(e.year) г."
        journalEntries.insert("\(dateStr) — \(e.title)\n\(e.details)", at: 0)
        banner("\(dateStr)\n\(e.title)")

        switch e.tag {
        case "alix":
            spawnAlexandra(animated: true)
        case "death":
            applyAccession(animated: true)
        case "coronation":
            let burst = SCNParticleSystem()
            burst.birthRate = 600
            burst.emissionDuration = 2.0
            burst.loops = false
            burst.particleLifeSpan = 4
            burst.particleSize = 0.08
            burst.particleVelocity = 7
            burst.particleVelocityVariation = 3
            burst.emittingDirection = SCNVector3(0, 1, 0)
            burst.spreadingAngle = 60
            burst.particleImage = Textures.snowflake
            burst.particleColor = UIColor(red: 1.0, green: 0.85, blue: 0.3, alpha: 1)
            let node = SCNNode()
            node.position = player.root.position + SCNVector3(0, 1, 0)
            node.addParticleSystem(burst)
            scene.rootNode.addChildNode(node)
            DispatchQueue.main.asyncAfter(deadline: .now() + 8) { node.removeFromParentNode() }
        default:
            break
        }
    }

    // MARK: - World mutations (shared by live events and save restoration)

    private func spawnAlexandra(animated: Bool) {
        guard let alix = pendingAlexandra else { return }
        if animated { alix.root.opacity = 0 }
        _ = addNPC(alix, "alix", x: 7, z: 6, wander: 4, seed: 77)
        if animated { alix.root.runAction(SCNAction.fadeIn(duration: 2.0)) }
        pendingAlexandra = nil
    }

    private func applyAccession(animated: Bool) {
        accession = true
        titleLabel.text = "Императоръ Всероссійскій Николай II"
        if let alex = alexanderNPC {
            if animated {
                alex.character.root.runAction(SCNAction.sequence([
                    SCNAction.fadeOut(duration: 2.5),
                    SCNAction.removeFromParentNode()
                ]))
            } else {
                alex.character.root.removeFromParentNode()
            }
            npcs.removeAll { $0 === alex }
            alexanderNPC = nil
        }
        // the Dowager Empress goes into mourning
        if let maria = mariaCharacter {
            for m in maria.clothMaterials {
                m.diffuse.contents = UIColor(white: 0.05, alpha: 1)
            }
        }
    }

    // MARK: - Persistence

    private func currentSave() -> GameSave {
        return GameSave(year: clock.year, month: clock.month, day: clock.day, hour: clock.hour,
                        accession: accession,
                        metPersonas: Array(metPersonas),
                        journal: journalEntries,
                        playerX: player.root.position.x,
                        playerZ: player.root.position.z,
                        speedMultiplier: clock.speedMultiplier)
    }

    private func applyRestoredState(_ s: GameSave) {
        clock.restore(year: s.year, month: s.month, day: s.day, hour: s.hour)
        clock.speedMultiplier = s.speedMultiplier
        if s.speedMultiplier > 1 { speedButton.setTitle("⏩ ×8", for: .normal) }
        metPersonas = Set(s.metPersonas)
        journalEntries = s.journal
        player.root.position = SCNVector3(s.playerX, 0, s.playerZ)
        rigNode.position = SCNVector3(s.playerX, 1.6, s.playerZ)

        let afterAlixArrival = s.year > 1894
            || (s.year == 1894 && (s.month > 10 || (s.month == 10 && s.day >= 10)))
        if afterAlixArrival { spawnAlexandra(animated: false) }
        if s.accession { applyAccession(animated: false) }

        let introSubtitle = introPanel.viewWithTag(802) as? UILabel
        introSubtitle?.text = "С.-Петербургъ • Дворцовая площадь • \(clock.dateString)"
    }

    // MARK: - Game loop

    @objc private func step(_ link: CADisplayLink) {
        var dt = Float(link.timestamp - lastTimestamp)
        lastTimestamp = link.timestamp
        if dt <= 0 || dt > 0.1 { dt = 1.0 / 60.0 }
        guard started else { return }

        updatePlayer(dt: dt)
        updateCamera(dt: dt)
        updateNPCs(dt: dt)
        updateClockAndSky(dt: dt)
        engine.update(frameDt: dt,
                      context: EngineContext(scene: scene, clock: clock,
                                             playerPosition: player.root.position))
    }

    private func updatePlayer(dt: Float) {
        let v = joystick.vector
        let mag = Float(min(1.0, sqrt(v.x * v.x + v.y * v.y)))

        if dialoguePanel.isHidden && mag > 0.08 {
            // camera looks along f = (sin(camYaw), cos(camYaw)); screen-right is f × up
            let fx = sinf(camYaw), fz = cosf(camYaw)
            let rx = -cosf(camYaw), rz = sinf(camYaw)
            var dx = fx * Float(v.y) + rx * Float(v.x)
            var dz = fz * Float(v.y) + rz * Float(v.x)
            let len = sqrtf(dx * dx + dz * dz)
            if len > 0.001 { dx /= len; dz /= len }

            let speed = 3.4 * mag
            playerYaw = approachAngle(playerYaw, atan2f(dx, dz), dt * 10)
            player.root.eulerAngles.y = playerYaw

            var pos = player.root.position
            let radius: Float = 0.45
            let nx = pos.x + dx * speed * dt
            if !hitsAny(nx, pos.z, radius) { pos.x = nx }
            let nz = pos.z + dz * speed * dt
            if !hitsAny(pos.x, nz, radius) { pos.z = nz }
            pos.x = max(-95, min(95, pos.x))
            pos.z = max(-50, min(52, pos.z))
            player.root.position = pos
            player.updateWalk(dt: dt, speed: speed)
        } else {
            player.updateWalk(dt: dt, speed: 0)
        }

        // snow field follows the player
        if let snow = snowNode {
            snow.position = SCNVector3(player.root.position.x, 24, player.root.position.z)
        }
    }

    private func hitsAny(_ x: Float, _ z: Float, _ radius: Float) -> Bool {
        for c in colliders where c.contains(x: x, z: z, radius: radius) {
            return true
        }
        return false
    }

    private func updateCamera(dt: Float) {
        let target = player.root.position + SCNVector3(0, 1.6, 0)
        let k = min(1.0, dt * 8)
        rigNode.position = SCNVector3(
            lerpf(rigNode.position.x, target.x, k),
            lerpf(rigNode.position.y, target.y, k),
            lerpf(rigNode.position.z, target.z, k)
        )
    }

    private func updateNPCs(dt: Float) {
        var nearest: NPC?
        var nearestDist: Float = 3.2
        for npc in npcs {
            npc.update(dt: dt, playerPos: player.root.position)
            let d = (npc.position - player.root.position).length
            if d < nearestDist {
                nearest = npc
                nearestDist = d
            }
        }
        if nearest !== activeNPC {
            activeNPC = nearest
            if let npc = nearest, let persona = GameData.personas[npc.personaId], dialoguePanel.isHidden {
                interactButton.setTitle("Говорить: \(persona.name)", for: .normal)
                interactButton.isHidden = false
            } else {
                interactButton.isHidden = true
                dialoguePanel.isHidden = true
            }
        } else if nearest == nil {
            interactButton.isHidden = true
        }
    }

    private func updateClockAndSky(dt: Float) {
        let fired = clock.advance(dt: Double(dt))
        for e in fired { fire(e) }

        if clock.day != lastShownDay {
            lastShownDay = clock.day
            dateLabel.text = "\(clock.dateString) (ст. ст.)"
            // autosave: a long historical campaign is never lost
            if started { SaveSystem.save(currentSave()) }
        }

        // day-night cycle
        let elevation = sinf((Float(clock.hour) - 6) / 12 * Float.pi)
        let dayFactor = max(0, min(1, elevation * 1.4))

        sunNode.eulerAngles.x = -(0.15 + max(elevation, 0) * 0.75)
        sunNode.light?.intensity = CGFloat(150 + dayFactor * 750)
        ambientNode.light?.intensity = CGFloat(180 + dayFactor * 380)

        let night = (r: Float(0.045), g: Float(0.06), b: Float(0.11))
        let day = (r: Float(0.63), g: Float(0.70), b: Float(0.78))
        let sky = UIColor(red: CGFloat(lerpf(night.r, day.r, dayFactor)),
                          green: CGFloat(lerpf(night.g, day.g, dayFactor)),
                          blue: CGFloat(lerpf(night.b, day.b, dayFactor)),
                          alpha: 1)
        scene.background.contents = sky
        scene.fogColor = sky
    }
}
