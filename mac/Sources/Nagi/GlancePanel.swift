import AppKit
import WebKit
import NagiCore

/// A borderless, non-activating panel: it takes keys without stealing the
/// frontmost app, like Apple's own menu-bar extras.
final class GlancePanel: NSPanel {
    var onCancel: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func cancelOperation(_ sender: Any?) { onCancel?() }
}

/// The same read-only web glance as Linux, in a rounded panel under the menu bar.
///
/// Opening is instant and never blank: the page stays loaded between opens and shows
/// its last render at once, then refreshes its data in place. Native code alone mints
/// sessions. When the page's session nears its 900 s limit (on open, every 12 minutes
/// while open, or after a 401) a fresh page loads underneath and replaces the visible
/// one only once it has rendered.
@MainActor final class GlancePanelController: NSObject, WKNavigationDelegate, WKScriptMessageHandler, NSWindowDelegate {
    private static let retryDelays: [UInt64] = [1, 2, 4]
    private static let handlers = ["nagiAuth", "nagiPanel"]
    /// The panel's --bg (web/glance-v2.css) for each appearance, so no frame is ever blank.
    private static let panelColour = NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            ? NSColor(srgbRed: 0x18 / 255.0, green: 0x13 / 255.0, blue: 0x1d / 255.0, alpha: 1)
            : NSColor(srgbRed: 0xf2 / 255.0, green: 0xf0 / 255.0, blue: 0xf6 / 255.0, alpha: 1)
    }

    /// One loaded glance document and the session it was minted with.
    private final class Page {
        let view: WKWebView
        var bootstrap: URL?
        var startedAt: Date?
        var ready = false
        init(_ view: WKWebView) { self.view = view }
    }

    private let config: NagiConfig?
    private let panel: GlancePanel
    private let dataStore = WKWebsiteDataStore.nonPersistent()
    private let webHost = NSView()
    private let messageView = NSStackView()
    private let messageLabel = NSTextField(wrappingLabelWithString: "Connecting to Nagi…")
    private var current: Page!
    private var pending: Page?
    private var lifecycle = NativeSessionLifecycle()
    private var refreshTimer: Timer?
    private var height = PanelGeometry.maxHeight
    private var sizePending = false
    /// A sheet asked for from the menu before the page was ready: settings or sources.
    private var sheetPending: String?
    private var retries = 0
    private var outsideMonitor: Any?
    private var keyMonitor: Any?
    private var activationMonitor: Any?
    /// The owner's last real click or Return in the panel: what lets a link open outside it.
    private var activation = ActivationGate()
    private var activationObserver: NSObjectProtocol?

    var anchor: (() -> NSRect?)?
    var onVisibilityChange: ((Bool) -> Void)?

    init(config: NagiConfig?) {
        self.config = config
        panel = GlancePanel(contentRect: NSRect(x: 0, y: 0, width: PanelGeometry.width, height: PanelGeometry.maxHeight),
                            styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: true)
        super.init()
        buildPanel()
        current = Page(makeWebView())
        current.view.isHidden = true
        webHost.addSubview(current.view)
        if config == nil { showMessage("Nagi isn't set up on this computer. Run mac/setup-mac.sh, then open Nagi again.") }
    }

    private func makeWebView() -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // One in-memory store for every page, so per-view swaps keep the page's local state.
        configuration.websiteDataStore = dataStore
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        // Marks the page as the Mac shell for the Mac-only density rules in the shared CSS.
        configuration.userContentController.addUserScript(WKUserScript(
            source: "document.documentElement.dataset.shell = 'mac';", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        for name in Self.handlers { configuration.userContentController.add(self, name: name) }
        let view = WKWebView(frame: webHost.bounds, configuration: configuration)
        view.autoresizingMask = [.width, .height]
        view.navigationDelegate = self
        view.allowsBackForwardNavigationGestures = false
        view.allowsMagnification = false
        // Mac density: real relayout at 0.85, so text stays vector-sharp (never a transform scale).
        view.pageZoom = CGFloat(PanelGeometry.zoom)
        view.underPageBackgroundColor = Self.panelColour
        return view
    }

    private func discard(_ page: Page) {
        page.view.stopLoading()
        page.view.removeFromSuperview()
        for name in Self.handlers { page.view.configuration.userContentController.removeScriptMessageHandler(forName: name) }
    }

    private func buildPanel() {
        panel.isFloatingPanel = true
        panel.level = .popUpMenu
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovable = false
        panel.isReleasedWhenClosed = false
        panel.animationBehavior = .none
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient, .ignoresCycle]
        panel.delegate = self
        panel.onCancel = { [weak self] in self?.hide() }

        let radius = CGFloat(PanelGeometry.cornerRadius)
        let effect = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: PanelGeometry.width, height: PanelGeometry.maxHeight))
        effect.material = .popover
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.maskImage = Self.roundedMask(radius: radius)
        effect.autoresizingMask = [.width, .height]
        panel.contentView = effect

        // The host is painted the panel colour, so a page that hasn't drawn yet never shows through.
        webHost.frame = effect.bounds
        webHost.autoresizingMask = [.width, .height]
        webHost.wantsLayer = true
        webHost.layer?.cornerRadius = radius
        webHost.layer?.masksToBounds = true
        effect.addSubview(webHost)
        syncHostColour()

        let retry = NSButton(title: "Try again", target: self, action: #selector(retryNow))
        retry.bezelStyle = .rounded
        messageLabel.preferredMaxLayoutWidth = CGFloat(PanelGeometry.width) - 48
        messageView.orientation = .vertical
        messageView.alignment = .leading
        messageView.spacing = 16
        messageView.edgeInsets = NSEdgeInsets(top: 24, left: 24, bottom: 24, right: 24)
        messageView.addArrangedSubview(messageLabel)
        messageView.addArrangedSubview(retry)
        messageView.frame = effect.bounds
        messageView.autoresizingMask = [.width, .height]
        effect.addSubview(messageView)
    }

    private func syncHostColour() {
        panel.effectiveAppearance.performAsCurrentDrawingAppearance {
            webHost.layer?.backgroundColor = Self.panelColour.cgColor
        }
    }

    private static func roundedMask(radius: CGFloat) -> NSImage {
        let edge = radius * 2 + 1
        let image = NSImage(size: NSSize(width: edge, height: edge), flipped: false) { rect in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
            return true
        }
        image.capInsets = NSEdgeInsets(top: radius, left: radius, bottom: radius, right: radius)
        image.resizingMode = .stretch
        return image
    }

    // MARK: Showing and hiding

    /// The status item's press: open at once, or close if open. No timers, no network first.
    func toggle() {
        if panel.isVisible { hide() } else { show() }
    }

    func show() {
        guard !panel.isVisible else { return }
        place()
        syncHostColour()
        sizePending = true
        panel.makeKeyAndOrderFront(nil)
        panel.orderFrontRegardless()
        panel.makeFirstResponder(current.view.isHidden ? nil : current.view)
        startMonitors()
        onVisibilityChange?(true)
        guard config != nil else { return }
        lifecycle.shown()
        retries = 0
        switch NativeSessionLifecycle.onShow(pageReady: current.ready, sessionStartedAt: current.startedAt, now: Date()) {
        case .refreshInPlace:
            evaluate("window.NagiGlance && void (window.NagiGlance.reopen || window.NagiGlance.refresh)()")
            runPendingSheet()
        case .remint:
            remint()
        }
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: NativeSessionLifecycle.refreshInterval, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.remint() }
        }
    }

    func hide() {
        guard panel.isVisible else { return }
        lifecycle.hidden()
        refreshTimer?.invalidate()
        refreshTimer = nil
        if let pending { discard(pending) }
        pending = nil
        stopMonitors()
        panel.orderOut(nil)
        onVisibilityChange?(false)
    }

    func openSettings() { openSheet("openSettings") }

    /// Settings → Sources, where sources are added and removed (window.NagiGlance.openSources).
    func openSources() { openSheet("openSources") }

    private func openSheet(_ function: String) {
        sheetPending = function
        if panel.isVisible && current.ready { runPendingSheet() } else { show() }
    }

    private func evaluate(_ script: String) {
        current.view.evaluateJavaScript(script, completionHandler: nil)
    }

    private func runPendingSheet() {
        guard let function = sheetPending, ["openSettings", "openSources"].contains(function) else { return }
        sheetPending = nil
        evaluate("window.NagiGlance && window.NagiGlance.\(function) && void window.NagiGlance.\(function)()")
    }

    private func place() {
        let fallback = NSScreen.main ?? NSScreen.screens.first
        let item = anchor?() ?? nil
        let screen = item.flatMap { frame in NSScreen.screens.first { $0.frame.intersects(frame) } } ?? fallback
        guard let screen else { return }
        let visible = screen.visibleFrame
        let itemFrame = item ?? NSRect(x: visible.maxX, y: visible.maxY, width: 0, height: 0)
        // Whole backing pixels, so the web content is never resampled.
        let frame = panel.backingAlignedRect(PanelGeometry.frame(item: itemFrame, visible: visible, height: height),
                                             options: .alignAllEdgesNearest)
        panel.setFrame(frame, display: true)
        panel.invalidateShadow()
    }

    private func startMonitors() {
        stopMonitors()
        // Clicks in other apps close the panel. Clicks on Nagi's own status item never
        // reach this monitor, so the item's press alone decides open or close.
        outsideMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown]) { [weak self] _ in
            Task { @MainActor [weak self] in self?.hide() }
        }
        // Switching apps (⌘-Tab, Dock, Spotlight) closes it too.
        activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main) { [weak self] note in
            let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
            guard app?.processIdentifier != ProcessInfo.processInfo.processIdentifier else { return }
            Task { @MainActor [weak self] in self?.hide() }
        }
        // Esc while the native message shows; the page handles its own Esc.
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard event.keyCode == 53 else { return event }
            let handled = MainActor.assumeIsolated { () -> Bool in
                guard let self, self.panel.isKeyWindow, self.current.view.isHidden else { return false }
                self.hide()
                return true
            }
            return handled ? nil : event
        }
        // Real input only: AppKit delivers these, a page cannot make them. The navigation
        // policy asks for one before it lets a GitHub link leave the panel.
        activationMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseUp, .keyDown]) { [weak self] event in
            let real = event.type == .leftMouseUp || (event.type == .keyDown && ActivationGate.activates(keyCode: event.keyCode))
            guard real else { return event }
            let stamp = event.timestamp
            let window = event.windowNumber
            MainActor.assumeIsolated {
                guard let self, self.panel.windowNumber == window else { return }
                self.activation.record(at: stamp)
            }
            return event
        }
    }

    private func stopMonitors() {
        if let outsideMonitor { NSEvent.removeMonitor(outsideMonitor) }
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
        if let activationMonitor { NSEvent.removeMonitor(activationMonitor) }
        activationMonitor = nil
        if let activationObserver { NSWorkspace.shared.notificationCenter.removeObserver(activationObserver) }
        outsideMonitor = nil
        keyMonitor = nil
        activationObserver = nil
    }

    // Key status is not used to close the panel: a status-item press can briefly take
    // key, which closed the panel the moment it opened. Outside clicks, app switches,
    // Esc and the item close it instead.

    // MARK: Sessions

    @objc private func retryNow() {
        retries = 0
        showMessage("Connecting to Nagi…")
        remint()
    }

    /// Mint a launch ticket natively and load it: into the visible view the first time,
    /// otherwise into a hidden replacement that swaps in once it has rendered.
    private func remint() {
        guard let config, let generation = lifecycle.begin() else { return }
        Task { @MainActor in
            do {
                let launch = try await OwnerSession.launch(page: config.page, directory: config.dataDirectory)
                guard lifecycle.complete(generation) else { return }
                retries = 0
                let page: Page
                if current.ready {
                    if let pending { discard(pending) }
                    page = Page(makeWebView())
                    // Underneath the visible page: it renders normally but is never seen until ready.
                    webHost.addSubview(page.view, positioned: .below, relativeTo: current.view)
                    pending = page
                } else {
                    page = current
                    page.ready = false
                }
                page.bootstrap = launch
                page.startedAt = Date()
                var request = URLRequest(url: launch)
                request.cachePolicy = .reloadIgnoringLocalCacheData
                request.timeoutInterval = 20
                page.view.load(request)
            } catch {
                guard lifecycle.complete(generation) else { return }
                kickstartReader()
                if retries < Self.retryDelays.count {
                    let delay = Self.retryDelays[retries]
                    retries += 1
                    try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
                    if panel.isVisible { remint() }
                } else if !current.ready {
                    showMessage("Nagi’s local reader is unavailable. Start it, then try again.")
                }
            }
        }
    }

    /// The LaunchAgent owns the reader; kickstart starts it only if it isn't running.
    private func kickstartReader() {
        let supervisor = Process()
        supervisor.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        supervisor.arguments = ["kickstart", "gui/\(getuid())/local.nagi.reader"]
        supervisor.standardOutput = FileHandle.nullDevice
        supervisor.standardError = FileHandle.nullDevice
        try? supervisor.run()
    }

    private func page(for view: WKWebView?) -> Page? {
        guard let view else { return nil }
        if current.view === view { return current }
        if let pending, pending.view === view { return pending }
        return nil
    }

    private func showMessage(_ text: String) {
        messageLabel.stringValue = text
        messageView.isHidden = false
        current.view.isHidden = true
    }

    private func showPage() {
        messageView.isHidden = true
        current.view.isHidden = false
        if panel.isKeyWindow { panel.makeFirstResponder(current.view) }
    }

    /// The glance page itself, or the one-use bootstrap URL that loads it.
    private func trusted(_ url: URL?, in page: Page) -> Bool {
        guard let url, let glance = config?.page else { return false }
        if let bootstrap = page.bootstrap, url == bootstrap { return true }
        return SourceLinks.privateURL(url, sameOriginAs: glance) && url.path == "/glance"
    }

    // MARK: Page messages

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let page = page(for: message.webView), message.frameInfo.isMainFrame,
              trusted(message.frameInfo.request.url, in: page), let body = message.body as? String else { return }
        if message.name == "nagiAuth" {
            if body == "reauthenticate", panel.isVisible {
                if page !== current, let pending { discard(pending); self.pending = nil }
                remint()
            }
            return
        }
        guard message.name == "nagiPanel", let parsed = PanelGeometry.message(body) else { return }
        switch parsed {
        case .ready:
            page.ready = true
            if page === pending {
                // The replacement has rendered: swap it in with no blank frame.
                let old = current!
                current = page
                pending = nil
                discard(old)
            }
            showPage()
            runPendingSheet()
        case .close:
            if page === current { hide() }
        case .height(let value):
            height = PanelGeometry.points(css: value)
            if page === current, sizePending, panel.isVisible {
                sizePending = false // the panel resizes only on open
                place()
            }
        }
    }

    // MARK: Navigation policy

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url, let page = page(for: webView) else {
            decisionHandler(.cancel)
            return
        }
        if navigationAction.navigationType == .linkActivated {
            // Rows open generated T3 thread links outside the panel, and CI marks plain GitHub
            // links; nothing else leaves it.
            if trusted(webView.url, in: page), SourceLinks.threadLinks(url.absoluteString) != nil {
                decisionHandler(.cancel)
                if ThreadOpener.open(url.absoluteString) { hide() }
                return
            }
            // A checks, deployment or pull request mark opens its GitHub page in the default
            // browser, and only on the owner's own click or Return: "link activated" alone is
            // true of a click a script made up. The navigation must start in the trusted main
            // frame, and a real mouse or key event in the panel must have come just before it.
            if let link = SourceLinks.githubLink(url.absoluteString), let target = URL(string: link) {
                decisionHandler(.cancel)
                let source = navigationAction.sourceFrame
                let fromPanel = trusted(webView.url, in: page) && source?.isMainFrame == true
                    && trusted(source?.request.url, in: page)
                let owned = activation.consume(at: ProcessInfo.processInfo.systemUptime)
                if fromPanel, owned, NSWorkspace.shared.open(target) { hide() }
                return
            }
        }
        let mainFrame = navigationAction.targetFrame?.isMainFrame == true
        decisionHandler(mainFrame && trusted(url, in: page) ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let response = navigationResponse.response as? HTTPURLResponse, response.statusCode != 200 {
            decisionHandler(.cancel)
            failed(webView, response.statusCode == 404
                ? "Quick glance isn’t available in this reader. Update this computer’s Nagi checkout, then try again."
                : "Nagi’s updates are unavailable. Check this computer’s local reader, then try again.")
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        showFailure(webView, error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        showFailure(webView, error)
    }

    private func showFailure(_ webView: WKWebView, _ error: Error) {
        let reason = error as NSError
        if reason.domain == NSURLErrorDomain && reason.code == NSURLErrorCancelled { return }
        // WebKit reports cancellation after the delegate handles a response or link.
        if reason.domain == "WebKitErrorDomain" && reason.code == 102 { return }
        failed(webView, "Can’t reach Nagi on this computer. Check that its local reader is running, then try again.")
    }

    /// A failed replacement is dropped and the visible page stays; a failed first load explains itself.
    private func failed(_ webView: WKWebView, _ text: String) {
        if let pending, pending.view === webView {
            discard(pending)
            self.pending = nil
        } else if webView === current.view, !current.ready {
            showMessage(text)
        }
    }
}
