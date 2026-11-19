import Foundation

/// Source-qualified thread transitions and quota-window warnings.
public struct NotificationEvent: Codable, Equatable, Sendable {
    public struct Links: Codable, Equatable, Sendable {
        public let desktop: String?
        public let web: String?
        public init(desktop: String?, web: String?) { self.desktop = desktop; self.web = web }
    }
    public let id: String
    public let kind: String
    public let threadId: String
    public let projectId: String
    public let threadTitle: String
    public let projectTitle: String
    public let occurredAt: String
    public let links: Links?
    public let provider: String?
    public let accountId: String?
    public let accountLabel: String?
    public let windowId: String?
    public let windowLabel: String?
    public let remainingPercent: Double?
    public let resetsAt: String?

    private enum CodingKeys: String, CodingKey, CaseIterable {
        case id, kind, threadId, projectId, threadTitle, projectTitle, occurredAt, links
        case provider, accountId, accountLabel, windowId, windowLabel, remainingPercent, resetsAt, repo
    }

    public init(id: String, kind: String, threadId: String, projectId: String, threadTitle: String,
                projectTitle: String, occurredAt: String, links: Links?) {
        self.id = id; self.kind = kind; self.threadId = threadId; self.projectId = projectId
        self.threadTitle = threadTitle; self.projectTitle = projectTitle; self.occurredAt = occurredAt; self.links = links
        provider = nil; accountId = nil; accountLabel = nil; windowId = nil; windowLabel = nil
        remainingPercent = nil; resetsAt = nil
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        kind = try c.decode(String.self, forKey: .kind)
        occurredAt = try c.decode(String.self, forKey: .occurredAt)
        links = try c.decodeIfPresent(Links.self, forKey: .links)
        if kind == "low_limit" {
            provider = try c.decode(String.self, forKey: .provider)
            accountId = try c.decode(String.self, forKey: .accountId)
            accountLabel = try c.decode(String.self, forKey: .accountLabel)
            windowId = try c.decode(String.self, forKey: .windowId)
            windowLabel = try c.decode(String.self, forKey: .windowLabel)
            remainingPercent = try c.decode(Double.self, forKey: .remainingPercent)
            resetsAt = try c.decode(String.self, forKey: .resetsAt)
            guard ["codex", "claude", "cursor"].contains(provider ?? ""),
                  let percent = remainingPercent, percent.isFinite, (0...100).contains(percent),
                  let reset = resetsAt, Self.date(reset) != nil,
                  [accountId, accountLabel, windowId, windowLabel].allSatisfy({
                      guard let value = $0 else { return false }
                      return !value.isEmpty && value.count <= 512 && !value.unicodeScalars.contains(where: { $0.value < 32 })
                  }), links?.desktop == nil, links?.web == nil else { throw OwnerSession.Failure.unavailable }
            threadId = ""; projectId = "limits"; threadTitle = ""; projectTitle = "Nagi"
        } else if kind == "ci_failed" {
            let repo = try c.decode(String.self, forKey: .repo)
            guard repo.range(of: #"\A[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\z"#,
                             options: .regularExpression) != nil,
                  !repo.hasSuffix("/."), !repo.hasSuffix("/.."), Self.date(occurredAt) != nil,
                  links?.desktop == nil, links?.web == nil else { throw OwnerSession.Failure.unavailable }
            threadId = ""; projectId = repo; threadTitle = ""; projectTitle = repo
            provider = nil; accountId = nil; accountLabel = nil; windowId = nil; windowLabel = nil
            remainingPercent = nil; resetsAt = nil
        } else {
            guard kind == "failed" || kind == "stuck" else { throw OwnerSession.Failure.unavailable }
            threadId = try c.decode(String.self, forKey: .threadId)
            projectId = try c.decode(String.self, forKey: .projectId)
            threadTitle = try c.decode(String.self, forKey: .threadTitle)
            projectTitle = try c.decode(String.self, forKey: .projectTitle)
            provider = nil; accountId = nil; accountLabel = nil; windowId = nil; windowLabel = nil
            remainingPercent = nil; resetsAt = nil
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id); try c.encode(kind, forKey: .kind)
        try c.encode(occurredAt, forKey: .occurredAt); try c.encode(links, forKey: .links)
        if kind == "low_limit" {
            try c.encode(provider, forKey: .provider); try c.encode(accountId, forKey: .accountId)
            try c.encode(accountLabel, forKey: .accountLabel); try c.encode(windowId, forKey: .windowId)
            try c.encode(windowLabel, forKey: .windowLabel); try c.encode(remainingPercent, forKey: .remainingPercent)
            try c.encode(resetsAt, forKey: .resetsAt)
        } else if kind == "ci_failed" {
            try c.encode(projectId, forKey: .repo)
        } else {
            try c.encode(threadId, forKey: .threadId); try c.encode(projectId, forKey: .projectId)
            try c.encode(threadTitle, forKey: .threadTitle); try c.encode(projectTitle, forKey: .projectTitle)
        }
    }

    // Same parser as the tray: any number of fractional digits and any offset (a provider's
    // microsecond `+00:00` reset must never make the whole pending list undecodable).
    private static func date(_ value: String) -> Date? { NagiTime.parse(value) }

    public var opensPanel: Bool { kind == "low_limit" || kind == "ci_failed" }
    public var bannerTitle: String {
        if kind == "ci_failed" { return projectTitle }
        return opensPanel ? (accountLabel ?? "Account") + " · " + String(format: "%g", remainingPercent ?? 0) + "% left" : projectTitle + " · " + threadTitle
    }
    public var bannerBody: String {
        if kind == "ci_failed" { return "CI checks failed." }
        if opensPanel, let reset = resetsAt, let date = Self.date(reset) {
            let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.dateFormat = "EEE HH:mm"
            return "resets " + formatter.string(from: date)
        }
        return kind == "failed" ? "Thread failed." : "Thread has been inactive."
    }
}

/// A live 30-second reservation. Not a delivery claim.
public struct NotificationLease: Codable, Equatable, Sendable {
    public let reservation: String
    public let expiresAt: String
    public let event: NotificationEvent
    public init(reservation: String, expiresAt: String, event: NotificationEvent) {
        self.reservation = reservation; self.expiresAt = expiresAt; self.event = event
    }
}

/// A pending event and the source whose journal holds it (sources-api.md).
public struct PendingNotification: Decodable, Equatable, Sendable {
    public let sourceId: String
    public let event: NotificationEvent
    public init(sourceId: String, event: NotificationEvent) { self.sourceId = sourceId; self.event = event }

    /// Reserved legacy T3 and GitHub CI journals or 32 lowercase hex.
    public static func validSourceId(_ value: String) -> Bool {
        value == "legacy-t3" || value == "github-ci" || value.range(of: "\\A[0-9a-f]{32}\\z", options: .regularExpression) != nil
    }
}

/// The reader's per-source notification routes, as the relay sees them.
public protocol NotificationBackend: Sendable {
    func pendingEvents() async throws -> [PendingNotification]
    func reserve(_ pending: PendingNotification) async throws -> NotificationLease?
    func claim(_ pending: PendingNotification, reservation: String) async throws
    func release(_ pending: PendingNotification, reservation: String) async throws
}

/// Owner-proved reads of this computer's reader. Every call mints a fresh mutual proof.
public struct NagiClient: NotificationBackend {
    public let origin: String
    public let directory: String
    static let feedLimit = 8 * 1024 * 1024
    static let smallLimit = 1024 * 1024

    public init(origin: String, directory: String) {
        self.origin = origin
        self.directory = directory
    }

    public func get(_ path: String) async throws -> Data {
        try await OwnerSession.request(origin: origin, method: "GET", path: path, directory: directory, limit: Self.feedLimit)
    }

    private func post(_ path: String, _ body: [String: String]) async throws -> Data {
        let data = try JSONSerialization.data(withJSONObject: body)
        return try await OwnerSession.request(origin: origin, method: "POST", path: path, body: data,
                                              directory: directory, limit: Self.smallLimit)
    }

    private struct Events: Decodable { let version: Int; let events: [PendingNotification] }
    private struct Reserved: Decodable { let version: Int; let reserved: Bool; let lease: NotificationLease? }
    private struct Finished: Decodable { let version: Int }

    /// GET /api/sources/v1/notifications: every source's pending events, oldest first.
    public func pendingEvents() async throws -> [PendingNotification] {
        let value = try JSONDecoder().decode(Events.self, from: try await get("/api/sources/v1/notifications"))
        guard value.version == 1, value.events.count <= 256,
              value.events.allSatisfy({ PendingNotification.validSourceId($0.sourceId) }) else { throw OwnerSession.Failure.unavailable }
        return value.events
    }

    public func reserve(_ pending: PendingNotification) async throws -> NotificationLease? {
        let data = try await post("/api/sources/v1/notifications/reserve", ["sourceId": pending.sourceId, "id": pending.event.id])
        let value = try JSONDecoder().decode(Reserved.self, from: data)
        guard value.version == 1 else { throw OwnerSession.Failure.unavailable }
        guard value.reserved, let lease = value.lease, lease.event.id == pending.event.id else { return nil }
        return lease
    }

    public func claim(_ pending: PendingNotification, reservation: String) async throws {
        try await finish("claim", pending, reservation)
    }

    public func release(_ pending: PendingNotification, reservation: String) async throws {
        try await finish("release", pending, reservation)
    }

    private func finish(_ action: String, _ pending: PendingNotification, _ reservation: String) async throws {
        let data = try await post("/api/sources/v1/notifications/" + action,
                                  ["sourceId": pending.sourceId, "id": pending.event.id, "reservation": reservation])
        guard try JSONDecoder().decode(Finished.self, from: data).version == 1 else { throw OwnerSession.Failure.unavailable }
    }
}
