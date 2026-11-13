import Foundation

/// The menu-bar readout. A port of linux/tray.py and web/glance-model.js, checked
/// against the shared tests/tray-label-cases.json table.
public enum TrayLabel {
    public static let glyph = "凪"
    public static let readerDown = "–"
    public static let readerDownTooltip = "Nagi · can't reach its local reader"
    static let providers = ["codex", "claude", "cursor"]

    /// live, dated, not_set_up, unsupported, checking or never.
    public static func agentsMode(_ agents: [String: Any]?) -> String {
        let status = agents?["status"] as? String
        if status == "ok" || status == "quiet" { return "live" }
        if status == "last_known", agents?["data"] is [String: Any] { return "dated" }
        if status == "not_set_up" || status == "unsupported" { return status ?? "never" }
        if status == "unavailable", agents?["reason"] as? String == "checking" { return "checking" }
        return "never"
    }

    private static func number(_ value: Any?) -> Double? { (value as? NSNumber)?.doubleValue }

    static func count(_ counts: [String: Any], _ key: String) -> Int {
        (counts[key] as? NSNumber)?.intValue ?? 0
    }

    /// The account with a window at 0, only from a fresh `ok` account and an unexpired
    /// window (linux/tray.py fresh_empty). A dated or expired 0 is never "empty".
    static func freshEmpty(_ limits: [String: Any]?, now: Date) -> (account: [String: Any], window: [String: Any])? {
        let sources = limits?["providers"] as? [String: Any] ?? [:]
        for key in providers {
            guard let source = sources[key] as? [String: Any], source["status"] as? String == "ok",
                  let data = source["data"] as? [String: Any] else { continue }
            for account in data["accounts"] as? [[String: Any]] ?? [] {
                guard (account["status"] as? String ?? "ok") == "ok" else { continue }
                let all = (account["windows"] as? [[String: Any]] ?? []) + (account["secondaryWindows"] as? [[String: Any]] ?? [])
                for window in all {
                    guard let remaining = number(window["remainingPercent"]), remaining <= 0,
                          let reset = (window["resetsAt"] as? String).flatMap(NagiTime.parse), reset > now else { continue }
                    return (account, window)
                }
            }
        }
        return nil
    }

    /// The oldest check time behind any retained (last-known) quota, or nil.
    static func datedLimits(_ limits: [String: Any]?) -> Date? {
        let sources = limits?["providers"] as? [String: Any] ?? [:]
        var oldest: Date?
        for key in providers {
            guard let source = sources[key] as? [String: Any], let data = source["data"] as? [String: Any] else { continue }
            var stamps: [Any?] = source["status"] as? String == "last_known" ? [source["checkedAt"]] : []
            for account in data["accounts"] as? [[String: Any]] ?? [] where account["status"] as? String == "last_known" {
                stamps.append(account["checkedAt"])
            }
            for case let stamp as String in stamps {
                guard let at = NagiTime.parse(stamp) else { continue }
                if oldest == nil || at < oldest! { oldest = at }
            }
        }
        return oldest
    }

    private static func counts(_ glance: [String: Any]?) -> [String: Any] {
        let agents = glance?["agents"] as? [String: Any]
        let data = agents?["data"] as? [String: Any]
        return data?["counts"] as? [String: Any] ?? [:]
    }

    /// `3`, `3 · ●`, `3 · ?`, `3 · empty`, `–` (can't reach), `·` (not set up) or nothing.
    /// Unreachable replaces the count; then `?` outranks `●`, which outranks `empty`,
    /// which needs fresh, unexpired evidence.
    public static func label(glance: [String: Any]?, limits: [String: Any]?, now: Date = Date()) -> String {
        let mode = agentsMode(glance?["agents"] as? [String: Any])
        if mode == "checking" { return "" }
        if mode == "not_set_up" { return "·" }
        if mode != "live" { return readerDown }
        let counts = counts(glance)
        let empty = freshEmpty(limits, now: now) != nil
        let mark = count(counts, "waitingOnYou") > 0 ? "?" : count(counts, "stuck") > 0 ? "●" : empty ? "empty" : ""
        let running = count(counts, "running")
        return [running > 0 ? String(running) : "", mark].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// The status item's title: the glyph, then the label when there is one.
    public static func title(_ label: String) -> String {
        label.isEmpty ? glyph : glyph + " " + label
    }

    public static func tooltip(glance: [String: Any]?, limits: [String: Any]?, now: Date = Date(),
                               timeZone: TimeZone = .current) -> String {
        let agents = glance?["agents"] as? [String: Any]
        let mode = agentsMode(agents)
        if mode == "checking" { return "Nagi · checking T3 Code…" }
        if mode == "not_set_up" { return "Nagi · T3 Code isn't connected on this computer" }
        if mode != "live" {
            let since = (agents?["checkedAt"] as? String) ?? (agents?["attemptedAt"] as? String)
            if let since, let date = NagiTime.parse(since) {
                return "Nagi · can't reach T3 Code since " + NagiTime.format(date, "HH:mm", timeZone)
            }
            return "Nagi · can't reach T3 Code"
        }
        let counts = counts(glance)
        var text = "Nagi · \(count(counts, "running")) running"
        if count(counts, "waitingOnYou") > 0 { text += " · \(count(counts, "waitingOnYou")) asks you" }
        if count(counts, "stuck") > 0 { text += " · \(count(counts, "stuck")) stuck" }
        if let empty = freshEmpty(limits, now: now) {
            let name = empty.account["label"] as? String ?? "A limit"
            if let reset = empty.window["resetsAt"] as? String, let date = NagiTime.parse(reset) {
                text += " · \(name) is empty until " + NagiTime.format(date, "EEE d MMM HH:mm", timeZone)
            } else {
                text += " · \(name) is empty"
            }
        }
        // Retained quota is dated, never live.
        if let dated = datedLimits(limits) { text += " · limits as of " + NagiTime.format(dated, "HH:mm", timeZone) }
        return text
    }
}

extension TrayLabel {
    /// The menu-bar tooltip from the source envelope (GET /api/sources/v1/glance), a port of
    /// linux/tray.py sources_tooltip: one source reads exactly as before; several sum fresh,
    /// source-local counts only and say how many sources can't be read.
    public static func sourcesTooltip(_ envelope: [String: Any]?, now: Date = Date(), timeZone: TimeZone = .current) -> String {
        let sources = envelope?["sources"] as? [[String: Any]] ?? []
        if sources.isEmpty { return "Nagi · nothing connected yet" }
        if sources.count == 1 {
            let source = sources[0]
            let glance: [String: Any] = ["version": 2, "agents": source["agents"] ?? NSNull()]
            let limits: [String: Any] = ["providers": source["limits"] as? [String: Any] ?? [:]]
            return tooltip(glance: glance, limits: limits, now: now, timeZone: timeZone)
        }
        let live = sources.filter { agentsMode($0["agents"] as? [String: Any]) == "live" }
        if live.isEmpty { return "Nagi · can't read your sources" }
        func total(_ key: String) -> Int {
            live.reduce(0) { sum, source in
                let data = (source["agents"] as? [String: Any])?["data"] as? [String: Any]
                return sum + count(data?["counts"] as? [String: Any] ?? [:], key)
            }
        }
        var text = "Nagi · \(total("running")) running"
        if total("waitingOnYou") > 0 { text += " · \(total("waitingOnYou")) asks you" }
        if total("stuck") > 0 { text += " · \(total("stuck")) stuck" }
        if live.count < sources.count { text += " · \(sources.count - live.count) of \(sources.count) sources can't be read" }
        return text
    }
}

/// ISO 8601 with an offset or Z, with or without fractional seconds (Python isoformat).
public enum NagiTime {
    public static func parse(_ value: String) -> Date? {
        guard value.count <= 40 else { return nil }
        let trimmed = value.replacingOccurrences(of: "\\.[0-9]+", with: "", options: .regularExpression)
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: trimmed)
    }

    public static func format(_ date: Date, _ pattern: String, _ timeZone: TimeZone) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        formatter.dateFormat = pattern
        return formatter.string(from: date)
    }
}
