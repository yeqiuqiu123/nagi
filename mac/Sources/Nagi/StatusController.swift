import AppKit
import NagiCore

/// The menu-bar item: the 凪 glyph alone, with the summary in its tooltip. A left click
/// toggles the glance; a right or Control click opens Open Nagi, Settings…, Sources…,
/// Quit Nagi. Polls the source envelope every 20 s.
@MainActor final class StatusController: NSObject {
    static let pollSeconds: TimeInterval = 20

    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let client: NagiClient?
    private let menu = NSMenu()
    private var timer: Timer?
    private var polling = false

    var onToggle: (() -> Void)?
    var onOpen: (() -> Void)?
    var onSettings: (() -> Void)?
    var onSources: (() -> Void)?

    init(config: NagiConfig?) {
        client = config.map { NagiClient(origin: $0.origin, directory: $0.dataDirectory) }
        super.init()
        if let button = item.button {
            button.title = TrayLabel.title("")
            button.toolTip = "Nagi"
            button.target = self
            button.action = #selector(clicked(_:))
            button.sendAction(on: [.leftMouseDown, .rightMouseDown])
        }
        let open = NSMenuItem(title: "Open Nagi", action: #selector(openPanel), keyEquivalent: "")
        open.target = self
        let settings = NSMenuItem(title: "Settings…", action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        let sources = NSMenuItem(title: "Sources…", action: #selector(openSources), keyEquivalent: "")
        sources.target = self
        let quit = NSMenuItem(title: "Quit Nagi", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp
        menu.addItem(open)
        menu.addItem(settings)
        menu.addItem(sources)
        menu.addItem(.separator())
        menu.addItem(quit)
        if client == nil { show(tooltip: "Nagi · run ./install.sh to finish setup") }
    }

    /// The status item's frame in screen coordinates, for placing the panel.
    var anchorFrame: NSRect? {
        guard let button = item.button, let window = button.window else { return nil }
        return window.convertToScreen(button.convert(button.bounds, to: nil))
    }

    func setHighlighted(_ on: Bool) {
        // After the click's own tracking ends, so the item stays lit while the panel is open.
        DispatchQueue.main.async { [weak self] in
            MainActor.assumeIsolated { self?.item.button?.highlight(on) }
        }
    }

    func start() {
        poll()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: Self.pollSeconds, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.poll() }
        }
    }

    @objc private func clicked(_ sender: Any?) {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseDown || event?.modifierFlags.contains(.control) == true {
            showMenu()
        } else {
            onToggle?()
        }
    }

    private func showMenu() {
        guard let button = item.button else { return }
        button.highlight(true)
        let below = NSPoint(x: 0, y: button.isFlipped ? button.bounds.height + 5 : -5)
        menu.popUp(positioning: nil, at: below, in: button)
        button.highlight(false)
    }

    @objc private func openPanel() { onOpen?() }
    @objc private func openSettings() { onSettings?() }
    @objc private func openSources() { onSources?() }

    private func show(tooltip: String) {
        guard let button = item.button else { return }
        // The owner wants the glyph alone in the menu bar; the summary lives in the tooltip.
        button.title = TrayLabel.title("")
        button.toolTip = tooltip
        button.setAccessibilityLabel(tooltip)
    }

    private func poll() {
        guard let client, !polling else { return }
        polling = true
        Task { @MainActor [weak self] in
            do {
                let data = try await client.get("/api/sources/v1/glance")
                let envelope = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                if envelope?["version"] as? Int == 1, envelope?["sources"] is [Any] {
                    self?.show(tooltip: TrayLabel.sourcesTooltip(envelope))
                } else {
                    self?.show(tooltip: TrayLabel.readerDownTooltip)
                }
            } catch {
                self?.show(tooltip: TrayLabel.readerDownTooltip)
            }
            self?.polling = false
        }
    }
}
