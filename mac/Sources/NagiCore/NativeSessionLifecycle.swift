import Foundation

// Native-owned scheduling only; JavaScript cannot mint or extend sessions.
public struct NativeSessionLifecycle {
    public static let refreshInterval: TimeInterval = 12 * 60
    public private(set) var visible = false
    private var pending = false
    private var generation = 0

    public init() {}

    public mutating func shown() { visible = true }
    public mutating func hidden() { visible = false; pending = false; generation += 1 }
    public mutating func begin() -> Int? {
        guard visible, !pending else { return nil }
        pending = true
        generation += 1
        return generation
    }
    public mutating func complete(_ generation: Int) -> Bool {
        guard generation == self.generation else { return false }
        pending = false
        return visible
    }

    public enum ShowAction: Equatable, Sendable {
        /// The loaded page's session is still fresh: refresh its data in place, no navigation.
        case refreshInPlace
        /// No page yet, or its session is near its 900 s limit: mint a new ticket.
        case remint
    }

    /// What a show does. Reusing a live page avoids a reload (and its blank frame) on
    /// every open; the session is never extended, only replaced by a new native mint.
    public static func onShow(pageReady: Bool, sessionStartedAt: Date?, now: Date) -> ShowAction {
        guard pageReady, let started = sessionStartedAt else { return .remint }
        let age = now.timeIntervalSince(started)
        return age >= 0 && age < refreshInterval ? .refreshInPlace : .remint
    }
}
