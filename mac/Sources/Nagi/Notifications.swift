import AppKit
import UserNotifications
import NagiCore

/// Failed and stuck banners through UserNotifications, with the reader's
/// reserve → post → claim/release protocol. A click opens the validated thread.
@MainActor final class NotificationController: NSObject, UNUserNotificationCenterDelegate {
    static let pollSeconds: TimeInterval = 20
    nonisolated static let linkKey = "nagiThreadLink"
    nonisolated static let panelKey = "nagiOpenPanel"
    var onOpenPanel: (() -> Void)? {
        didSet { if pendingPanel { pendingPanel = false; onOpenPanel?() } }
    }
    private var pendingPanel = false

    private let client: NagiClient?
    private var relay: NagiCore.NotificationRelay?
    private var timer: Timer?

    init(client: NagiClient?) {
        self.client = client
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    func start() {
        guard let client else { return }
        // First run asks once; a refusal leaves events pending and the glance usable.
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        relay = NotificationRelay(backend: client) { [weak self] event in
            await self?.post(event) ?? false
        }
        tick()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: Self.pollSeconds, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.tick() }
        }
    }

    private func tick() {
        guard let relay, !relay.busy else { return }
        Task { @MainActor in
            // Without permission there is no send, so nothing is reserved or claimed.
            guard await Self.authorized() else { return }
            await relay.poll()
        }
    }

    private static func authorized() async -> Bool {
        await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                let status = settings.authorizationStatus
                continuation.resume(returning: status == .authorized || status == .provisional)
            }
        }
    }

    /// True only when macOS accepted the request; that is the claim condition.
    private func post(_ event: NotificationEvent) async -> Bool {
        guard await Self.authorized() else { return false }
        let content = UNMutableNotificationContent()
        content.title = event.bannerTitle
        content.body = event.bannerBody
        content.threadIdentifier = event.projectId
        // A click opens the thread only through a validated link; a source without links still alerts.
        if let link = event.links?.desktop, SourceLinks.threadLinks(link) != nil {
            content.userInfo = [Self.linkKey: link]
        } else if event.opensPanel {
            content.userInfo = [Self.panelKey: true]
        }
        // The stable event ID replaces, never stacks, a banner re-sent after a crash.
        let request = UNNotificationRequest(identifier: event.id, content: content, trigger: nil)
        return await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            UNUserNotificationCenter.current().add(request) { error in
                continuation.resume(returning: error == nil)
            }
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler completionHandler: @escaping () -> Void) {
        let link = response.notification.request.content.userInfo[Self.linkKey] as? String
        let panel = response.notification.request.content.userInfo[Self.panelKey] as? Bool == true
        if response.actionIdentifier == UNNotificationDefaultActionIdentifier, panel {
            Task { @MainActor in
                if let open = self.onOpenPanel { open() } else { self.pendingPanel = true }
            }
        }
        if response.actionIdentifier == UNNotificationDefaultActionIdentifier, let link {
            Task { @MainActor in ThreadOpener.open(link) }
        }
        completionHandler()
    }
}
