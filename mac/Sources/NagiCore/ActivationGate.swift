import Foundation

/// Proof that a link leaving the panel came from the owner's own click or key press.
///
/// WebKit calls a navigation "link activated" whenever an event started it, including a
/// click a script made up, and it keeps whether the event was trusted to itself. The panel
/// therefore holds its own evidence: the last real left mouse-up or Return key-down that
/// AppKit delivered to the panel's window. A link may open outside the panel only when such
/// an event arrived just before its navigation, and each event vouches for one navigation.
/// This is the Mac's counterpart of `is_user_gesture()` in the Linux shells.
public struct ActivationGate: Sendable {
    /// How long after a real event its navigation may still arrive. The web process answers
    /// in milliseconds; the rest is room for a busy machine.
    public static let window: TimeInterval = 1.0

    private var last: TimeInterval?

    public init() {}

    /// Key codes that activate a focused link: Return and the keypad's Enter.
    public static func activates(keyCode: UInt16) -> Bool { keyCode == 36 || keyCode == 76 }

    /// A real left mouse-up or activating key-down in the panel, at its event timestamp
    /// (seconds since the system started).
    public mutating func record(at time: TimeInterval) { last = time }

    /// True once, for a navigation that closely follows a recorded event. False when there
    /// was no event, when it is stale or from the future, or when it was already used.
    public mutating func consume(at time: TimeInterval) -> Bool {
        guard let event = last else { return false }
        last = nil
        let age = time - event
        return age >= 0 && age <= Self.window
    }
}
