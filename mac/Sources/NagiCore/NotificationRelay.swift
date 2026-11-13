import Foundation

public enum DeliveryOutcome: Equatable, Sendable {
    case notReserved(String)
    case claimed(String)
    case released(String)
}

/// Reserve, post, then claim on a confirmed send or release on failure, exactly as
/// linux/agent_notifications.py, each against the source that holds the event. At-least-once: a crash between the OS accepting a
/// banner and the claim lets the lease expire and the event come back; the banner
/// reuses the event ID, so macOS replaces rather than stacks it. No send, no claim.
@MainActor public final class NotificationRelay {
    private let backend: NotificationBackend
    private let post: @MainActor (NotificationEvent) async -> Bool
    public private(set) var busy = false

    public init(backend: NotificationBackend, post: @escaping @MainActor (NotificationEvent) async -> Bool) {
        self.backend = backend
        self.post = post
    }

    /// One pass. Overlapping passes are skipped; any transport error ends the pass and
    /// leaves the remaining events pending for the next one.
    @discardableResult public func poll() async -> [DeliveryOutcome] {
        guard !busy else { return [] }
        busy = true
        defer { busy = false }
        var outcomes: [DeliveryOutcome] = []
        do {
            for candidate in try await backend.pendingEvents() {
                guard let lease = try await backend.reserve(candidate) else {
                    outcomes.append(.notReserved(candidate.event.id))
                    continue
                }
                let event = lease.event
                guard event == candidate.event else {
                    try await backend.release(candidate, reservation: lease.reservation)
                    outcomes.append(.released(candidate.event.id))
                    continue
                }
                if await post(event) {
                    try await backend.claim(candidate, reservation: lease.reservation)
                    outcomes.append(.claimed(event.id))
                } else {
                    try await backend.release(candidate, reservation: lease.reservation)
                    outcomes.append(.released(event.id))
                }
            }
        } catch {}
        return outcomes
    }
}
