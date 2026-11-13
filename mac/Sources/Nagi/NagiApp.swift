import AppKit
import NagiCore

/// Build-time settings from Info.plist (mac/build-app.sh). No network or file access.
struct NagiConfig {
    let page: URL
    let origin: String
    let dataDirectory: String

    static func load(_ bundle: Bundle = .main) -> NagiConfig? {
        guard let raw = bundle.object(forInfoDictionaryKey: "NagiGlanceURL") as? String,
              let page = URL(string: raw), page.path == "/glance", page.fragment == nil,
              SourceLinks.privateURL(page, sameOriginAs: page), let port = page.port,
              let directory = bundle.object(forInfoDictionaryKey: "NagiDataDirectory") as? String,
              directory.hasPrefix("/") else { return nil }
        return NagiConfig(page: page, origin: "http://127.0.0.1:\(port)", dataDirectory: directory)
    }
}

/// Opens only validated T3 thread links: the desktop app first, then the web fallback.
@MainActor enum ThreadOpener {
    @discardableResult static func open(_ value: String) -> Bool {
        SourceLinks.openThread(value,
                               hasDesktopHandler: { NSWorkspace.shared.urlForApplication(toOpen: $0) != nil },
                               open: { NSWorkspace.shared.open($0) })
    }
}

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
    private let config = NagiConfig.load()
    private var notifications: NotificationController?
    private var panel: GlancePanelController?
    private var status: StatusController?

    func applicationWillFinishLaunching(_ notification: Notification) {
        // The banner delegate must exist before launch finishes so a click that
        // launched Nagi still opens its thread.
        let client = config.map { NagiClient(origin: $0.origin, directory: $0.dataDirectory) }
        notifications = NotificationController(client: client)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let me = ProcessInfo.processInfo.processIdentifier
        if let id = Bundle.main.bundleIdentifier,
           NSRunningApplication.runningApplications(withBundleIdentifier: id).contains(where: { $0.processIdentifier != me }) {
            NSApp.terminate(nil)
            return
        }
        let panel = GlancePanelController(config: config)
        let status = StatusController(config: config)
        panel.anchor = { [weak status] in status?.anchorFrame }
        panel.onVisibilityChange = { [weak status] visible in status?.setHighlighted(visible) }
        status.onToggle = { [weak panel] in panel?.toggle() }
        status.onOpen = { [weak panel] in panel?.show() }
        status.onSettings = { [weak panel] in panel?.openSettings() }
        status.onSources = { [weak panel] in panel?.openSources() }
        self.panel = panel
        notifications?.onOpenPanel = { [weak panel] in panel?.show() }
        self.status = status
        status.start()
        notifications?.start()
    }
}

@main
enum NagiMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) { app.run() }
    }
}
