import Foundation
import Testing
import CoreGraphics
@testable import NagiCore

// Swift Testing ships with the Command Line Tools; XCTest does not.

@Suite struct LinkPolicy {
    let base = URL(string: "http://127.0.0.1:47831/glance")!

    @Test func glanceAndItsSectionsAreTheOnlyPrivatePages() {
        for path in ["/glance", "/glance#agents", "/glance#limits", "/glance#ended", "/overview", "/overview#ended"] {
            #expect(SourceLinks.privateURL(URL(string: "http://127.0.0.1:47831" + path)!, sameOriginAs: base), "\(path)")
        }
        for value in ["http://127.0.0.1:47831/glance?x=1", "http://127.0.0.1:47831/glance#unknown",
                      "http://127.0.0.1:47831/glance#", "http://127.0.0.1:47831/glance/",
                      "http://127.0.0.2:47831/glance", "http://127.0.0.1:47832/glance",
                      "http://user@127.0.0.1:47831/glance", "https://127.0.0.1:47831/glance",
                      "http://127.0.0.1:47831/api/glance", "http://localhost:47831/glance",
                      "https://retired.ts.net:9443/glance", "http://127.0.0.1:47831/company/tasks/22"] {
            #expect(!SourceLinks.privateURL(URL(string: value)!, sameOriginAs: base), "\(value)")
        }
    }

    @Test func threadLinksMatchThePythonPolicy() {
        // Values and outputs taken from nagi_links.thread_links.
        let cases: [(String, String)] = [
            ("t3code://threads/e/a%3Ab", "e/a%3Ab"),
            ("https://app.t3.codes/threads/local%3A1/abc", "local%3A1/abc"),
            ("t3code://threads/env/thr%C3%A9", "env/thr%C3%A9"),
            ("T3CODE://threads/e/a", "e/a"),
            ("t3code://threads/e/a%2Fb", "e/a%2Fb"),
            ("t3code://threads/e/%7E~", "e/~~"),
            ("t3code://threads/11111111-1111-4111-8111-111111111111/thread_01.x", "11111111-1111-4111-8111-111111111111/thread_01.x"),
        ]
        for (value, path) in cases {
            #expect(SourceLinks.threadLinks(value) == SourceLinks.ThreadLinks(
                desktop: "t3code://threads/" + path, web: "https://app.t3.codes/threads/" + path), "\(value)")
        }
        var rejected = ["file:///tmp/x", "t3code://threads/e/a?x=1", "t3code://threads/e/a\n", "t3code://threads/e/a%ZZ",
                        "https://evil/threads/e/a", "t3code://threads/e/a b", "t3code://threads/e/a#x",
                        "https://app.t3.codes.evil.example/threads/e/a", "https://user@app.t3.codes/threads/e/a",
                        "https://app.t3.codes:443/threads/e/a", "t3code://threads/e/a/b", "t3code://threads/e",
                        "t3code://threads/e/%00", "t3code://threads/e/%FF", "javascript:alert(1)",
                        "http://app.t3.codes/threads/e/a", "t3code://threads/e/" + String(repeating: "a", count: 513)]
        for base in ["t3code://threads/", "https://app.t3.codes/threads/"] {
            rejected += ["./a", "e/..", "%2e/a", "e/%2E%2e", "e/", "/a"].map { base + $0 }
        }
        for value in rejected { #expect(SourceLinks.threadLinks(value) == nil, "\(value)") }
    }

    @Test func desktopFirstThenWebFallback() {
        var opened: [String] = []
        #expect(SourceLinks.openThread("t3code://threads/e/a%3Ab", hasDesktopHandler: { _ in false },
                                       open: { opened.append($0.absoluteString); return true }))
        #expect(opened == ["https://app.t3.codes/threads/e/a%3Ab"])
        opened = []
        #expect(SourceLinks.openThread("https://app.t3.codes/threads/e/a", hasDesktopHandler: { _ in true },
                                       open: { opened.append($0.absoluteString); return $0.scheme == "https" }))
        #expect(opened == ["t3code://threads/e/a", "https://app.t3.codes/threads/e/a"])
        opened = []
        #expect(!SourceLinks.openThread("https://example.com/", hasDesktopHandler: { _ in true },
                                        open: { opened.append($0.absoluteString); return true }))
        #expect(opened.isEmpty)
    }
}

@Suite struct OwnerProofs {
    @Test func proofsMatchPython() {
        let args = (String(repeating: "a", count: 43), "http://127.0.0.1:47831", String(repeating: "i", count: 43),
                    String(repeating: "c", count: 43), String(repeating: "n", count: 43))
        let server = OwnerSession.hex(OwnerSession.mac(args.0, "nagi-server-v2", args.1, args.2, args.3, args.4,
                                                       "POST", "/auth/launch", String(repeating: "0", count: 64)))
        #expect(server == "fa191b67dec796a14985483ebb61cdf6f96b0effb019106bb9d82386cd1f8ce9")
        // A native GET of /api/glance hashes the empty body (owner_auth.authenticated_open).
        let empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        let get = OwnerSession.hex(OwnerSession.mac(args.0, "nagi-client-v2", args.1, args.2, args.3, args.4,
                                                    "GET", "/api/glance", empty))
        #expect(get == "fd7879beae73279b29e07f013f47c664f3d93fc328d7bc22e6771471e5a758ae")
        #expect(OwnerSession.nonce().count == 43)
        #expect(OwnerSession.decodeHex(server) != nil)
        #expect(OwnerSession.decodeHex("XYZ") == nil)
    }

    @Test func onlyExactLoopbackOrigins() {
        #expect(OwnerSession.validOrigin("http://127.0.0.1:47831"))
        for value in ["http://127.0.0.1:80", "http://127.0.0.1:65536", "http://localhost:47831", "https://127.0.0.1:47831",
                      "http://127.0.0.1:47831/", "http://127.0.0.2:47831", "http://127.0.0.1:047831"] {
            #expect(!OwnerSession.validOrigin(value), "\(value)")
        }
    }

    @Test func ownerFileMustBePrivateAndReal() throws {
        let manager = FileManager.default
        let directory = manager.temporaryDirectory.appendingPathComponent("nagi-owner-check-" + UUID().uuidString)
        try manager.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        defer { try? manager.removeItem(at: directory) }
        let path = directory.appendingPathComponent("nagi-owner.json")
        let secret = String(repeating: "a", count: 43)
        let data = try JSONSerialization.data(withJSONObject: ["version": 1, "secret": secret])
        manager.createFile(atPath: path.path, contents: data, attributes: [.posixPermissions: 0o600])
        #expect(try OwnerSession.secret(directory: directory.path) == secret)
        try manager.setAttributes([.posixPermissions: 0o644], ofItemAtPath: path.path)
        #expect(throws: OwnerSession.Failure.self) { try OwnerSession.secret(directory: directory.path) }
        try manager.removeItem(at: path)
        let original = directory.appendingPathComponent("original.json")
        manager.createFile(atPath: original.path, contents: data, attributes: [.posixPermissions: 0o600])
        try manager.createSymbolicLink(at: path, withDestinationURL: original)
        #expect(throws: OwnerSession.Failure.self) { try OwnerSession.secret(directory: directory.path) }
    }

    @Test func sessionLifecycleCoalescesAndDiscardsAfterHide() {
        #expect(NativeSessionLifecycle.refreshInterval == 720)
        var lifecycle = NativeSessionLifecycle()
        let hidden = lifecycle.begin()
        #expect(hidden == nil, "Hidden panels must not refresh")
        lifecycle.shown()
        let first = lifecycle.begin()!
        let coalesced = lifecycle.begin()
        #expect(coalesced == nil, "Coalesce simultaneous show/timer/401")
        let firstDone = lifecycle.complete(first)
        #expect(firstDone)
        lifecycle.shown()
        let next = lifecycle.begin()!
        let nextDone = lifecycle.complete(next)
        #expect(nextDone, "Every show can mint a fresh ticket")
        let signalled = lifecycle.begin()!
        lifecycle.hidden()
        let late = lifecycle.complete(signalled)
        #expect(!late, "Discard a completion after hide")
        let hiddenBegin = lifecycle.begin()
        #expect(hiddenBegin == nil)
        lifecycle.shown()
        let reopened = lifecycle.begin()
        #expect(reopened != nil, "Reopening recovers after a hidden request")
    }
}

@Suite struct ShowWithoutReload {
    @Test func aFreshPageRefreshesInPlaceAndAnOldOneIsReminted() {
        let now = Date()
        #expect(NativeSessionLifecycle.onShow(pageReady: true, sessionStartedAt: now.addingTimeInterval(-60), now: now) == .refreshInPlace)
        #expect(NativeSessionLifecycle.onShow(pageReady: true, sessionStartedAt: now.addingTimeInterval(-719), now: now) == .refreshInPlace)
        #expect(NativeSessionLifecycle.onShow(pageReady: true, sessionStartedAt: now.addingTimeInterval(-720), now: now) == .remint)
        #expect(NativeSessionLifecycle.onShow(pageReady: true, sessionStartedAt: now.addingTimeInterval(60), now: now) == .remint,
                "A clock step backwards never trusts a session")
        #expect(NativeSessionLifecycle.onShow(pageReady: false, sessionStartedAt: now, now: now) == .remint)
        #expect(NativeSessionLifecycle.onShow(pageReady: true, sessionStartedAt: nil, now: now) == .remint)
    }
}

@Suite struct TrayLabels {
    static let at = "2026-11-12T23:05:00+00:00"

    // The same fixtures as tests/test_glance_shell.py.
    static func glance(_ status: String, _ counts: [String: Any]?, _ reason: String?) -> [String: Any] {
        var data: Any = NSNull()
        if ["ok", "quiet", "last_known"].contains(status) {
            var merged: [String: Any] = ["running": 0, "waitingOnYou": 0, "stuck": 0, "ended": 0]
            for (key, value) in counts ?? [:] { merged[key] = value }
            data = ["projects": [], "ended": [], "counts": merged] as [String: Any]
        }
        let agents: [String: Any] = ["status": status, "attemptedAt": at, "checkedAt": data is NSNull ? NSNull() : at,
                                     "reason": reason ?? NSNull(), "data": data]
        return ["version": 2, "agents": agents]
    }

    static let now = NagiTime.parse(at)!

    static func limits(empty: Bool, _ variant: String? = nil) -> [String: Any] {
        let reset = variant == "expired" ? "2026-11-12T22:00:00Z" : "2026-11-16T14:58:29Z"
        let window: [String: Any] = ["id": "primary", "label": "Weekly", "kind": "weekly", "remainingPercent": empty ? 0 : 12,
                                     "resetsAt": reset, "checkedAt": at]
        var account: [String: Any] = ["id": "c", "label": "Codex 1", "windows": [window]]
        if variant == "account_last_known" {
            account["status"] = "last_known"; account["checkedAt"] = "2026-11-12T22:40:00+00:00"; account["reason"] = "probe_failed"
        }
        let ok: [String: Any] = ["status": variant == "last_known" ? "last_known" : "ok", "attemptedAt": at, "checkedAt": at,
                                 "reason": NSNull(), "warnings": [], "data": ["accounts": [account]]]
        let claude: [String: Any] = ["status": "not_set_up", "attemptedAt": at, "checkedAt": NSNull(), "reason": "not_installed",
                                     "warnings": [], "data": NSNull()]
        return ["version": 2, "providers": ["codex": ok, "claude": claude]]
    }

    /// Round-trip through JSON so values have the same types as a real response.
    static func json(_ value: [String: Any]) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: JSONSerialization.data(withJSONObject: value)) as! [String: Any]
    }

    @Test func sharedCaseTable() throws {
        let table = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("tests/tray-label-cases.json")
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: table)) as! [[String: Any]]
        #expect(cases.count >= 17)
        for item in cases {
            let agents = item["agents"] as! [String: Any]
            let glance = try Self.json(Self.glance(agents["status"] as! String, agents["counts"] as? [String: Any],
                                                   agents["reason"] as? String))
            let limits = try Self.json(Self.limits(empty: item["empty"] as! Bool, item["limits"] as? String))
            #expect(TrayLabel.label(glance: glance, limits: limits, now: Self.now) == item["expect"] as! String, "\(item["name"]!)")
        }
    }

    @Test func cursorProviderIsRecognizedByTheTray() throws {
        let original = try JSONSerialization.data(withJSONObject: Self.limits(empty: true))
        let renamed = String(decoding: original, as: UTF8.self)
            .replacingOccurrences(of: "codex", with: "cursor")
            .replacingOccurrences(of: "Codex 1", with: "Cursor 1")
        let limits = try JSONSerialization.jsonObject(with: Data(renamed.utf8)) as! [String: Any]
        #expect(TrayLabel.freshEmpty(limits, now: Self.now)?.account["label"] as? String == "Cursor 1")
        #expect(TrayLabel.label(glance: try Self.json(Self.glance("ok", ["running": 1], nil)),
                               limits: limits, now: Self.now) == "1 · empty")
    }

    @Test func titlesCarryTheGlyph() {
        #expect(TrayLabel.title("3") == "凪 3")
        #expect(TrayLabel.title("3 · empty") == "凪 3 · empty")
        #expect(TrayLabel.title("3 · ?") == "凪 3 · ?")
        #expect(TrayLabel.title("3 · ●") == "凪 3 · ●")
        #expect(TrayLabel.title("–") == "凪 –")
        #expect(TrayLabel.title("·") == "凪 ·")
        #expect(TrayLabel.title("") == "凪")
    }

    @Test func tooltipsFollowTheCopyDeck() throws {
        let utc = TimeZone(identifier: "UTC")!
        let calm = try Self.json(Self.limits(empty: false))
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("ok", ["running": 3], nil)), limits: calm) == "Nagi · 3 running")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("ok", ["running": 3, "stuck": 1, "waitingOnYou": 1], nil)),
                                  limits: calm) == "Nagi · 3 running · 1 asks you · 1 stuck")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("ok", ["running": 3], nil)),
                                  limits: try Self.json(Self.limits(empty: true)), now: Self.now, timeZone: utc)
                == "Nagi · 3 running · Codex 1 is empty until Mon 16 Nov 14:58")
        // Retained quota is dated, and a dated or expired 0 is not called empty.
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("ok", ["running": 1], nil)),
                                  limits: try Self.json(Self.limits(empty: true, "account_last_known")), now: Self.now, timeZone: utc)
                == "Nagi · 1 running · limits as of 22:40")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("ok", ["running": 1], nil)),
                                  limits: try Self.json(Self.limits(empty: true, "expired")), now: Self.now, timeZone: utc)
                == "Nagi · 1 running")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("last_known", ["running": 3], nil)), limits: calm, timeZone: utc)
                == "Nagi · can't reach T3 Code since 23:05")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("not_set_up", nil, "not_configured")), limits: calm)
                == "Nagi · T3 Code isn't connected on this computer")
        #expect(TrayLabel.tooltip(glance: try Self.json(Self.glance("unavailable", nil, "checking")), limits: calm)
                == "Nagi · checking T3 Code…")
    }

    // The same envelopes as tests/test_glance_shell.py.
    static func source(_ id: String, _ status: String, _ counts: [String: Any]) throws -> [String: Any] {
        let agents = try json(glance(status, counts, nil))["agents"]!
        return ["source": ["id": id, "harness": "t3", "label": id, "placement": "local"], "agents": agents, "limits": [String: Any]()]
    }

    @Test func sourcesTooltipFollowsTheLinuxTray() throws {
        var one = try Self.source("legacy-t3", "ok", ["running": 3])
        one["limits"] = (try Self.json(Self.limits(empty: false)))["providers"]
        #expect(TrayLabel.sourcesTooltip(["version": 1, "sources": [one]], now: Self.now) == "Nagi · 3 running")
        let live = try Self.source("a", "ok", ["running": 2, "stuck": 1])
        let other = try Self.source("b", "ok", ["running": 1, "waitingOnYou": 1])
        let down = try Self.source("c", "last_known", ["running": 9])
        #expect(TrayLabel.sourcesTooltip(["sources": []]) == "Nagi · nothing connected yet")
        #expect(TrayLabel.sourcesTooltip(["sources": [live, other, down]])
                == "Nagi · 3 running · 1 asks you · 1 stuck · 1 of 3 sources can't be read")
        #expect(TrayLabel.sourcesTooltip(["sources": [down, down]]) == "Nagi · can't read your sources")
    }

    @Test func pythonTimestampsParse() {
        #expect(NagiTime.parse("2026-11-12T23:05:00.123456+00:00") == NagiTime.parse("2026-11-12T23:05:00Z"))
        #expect(NagiTime.parse("2026-11-12T23:05:00Z") != nil)
        #expect(NagiTime.parse("yesterday") == nil)
    }
}

final class FakeBackend: NotificationBackend, @unchecked Sendable {
    var events: [NotificationEvent] = []
    /// Which source journal holds each event; defaults to the legacy T3 binding.
    var sources: [String: String] = [:]
    var reservable: Set<String> = []
    var failReserve = false
    var calls: [String] = []

    func source(_ id: String) -> String { sources[id] ?? "legacy-t3" }
    func pendingEvents() async throws -> [PendingNotification] {
        calls.append("list")
        return events.map { PendingNotification(sourceId: source($0.id), event: $0) }
    }
    func reserve(_ pending: PendingNotification) async throws -> NotificationLease? {
        let id = pending.event.id
        calls.append("reserve \(pending.sourceId) \(id)")
        if failReserve { throw OwnerSession.Failure.status(503) }
        guard pending.sourceId == source(id), reservable.contains(id),
              let event = events.first(where: { $0.id == id }) else { return nil }
        reservable.remove(id)
        return NotificationLease(reservation: "r-" + id, expiresAt: "2026-11-13T00:00:30Z", event: event)
    }
    func claim(_ pending: PendingNotification, reservation: String) async throws {
        calls.append("claim \(pending.sourceId) \(pending.event.id) \(reservation)")
        events.removeAll { $0.id == pending.event.id }
    }
    func release(_ pending: PendingNotification, reservation: String) async throws {
        calls.append("release \(pending.sourceId) \(pending.event.id) \(reservation)")
        reservable.insert(pending.event.id)
    }
}

@MainActor @Suite struct NotificationDelivery {
    static func event(_ id: String, _ kind: String = "failed") -> NotificationEvent {
        NotificationEvent(id: id, kind: kind, threadId: "t-" + id, projectId: "p", threadTitle: "Build", projectTitle: "Nagi",
                          occurredAt: "2026-11-13T00:00:00Z",
                          links: .init(desktop: "t3code://threads/e/t-" + id, web: "https://app.t3.codes/threads/e/t-" + id))
    }

    @Test func claimOnlyAfterAConfirmedSendAndReleaseOnFailure() async {
        let backend = FakeBackend()
        backend.events = [Self.event("a"), Self.event("b", "stuck"), Self.event("c")]
        backend.reservable = ["a", "b"]
        var posted: [String] = []
        let relay = NotificationRelay(backend: backend) { event in posted.append(event.id); return event.id == "a" }
        let outcomes = await relay.poll()
        #expect(outcomes == [.claimed("a"), .released("b"), .notReserved("c")])
        #expect(posted == ["a", "b"], "No send without a reservation")
        #expect(backend.calls == ["list", "reserve legacy-t3 a", "claim legacy-t3 a r-a", "reserve legacy-t3 b",
                                  "release legacy-t3 b r-b", "reserve legacy-t3 c"])
    }

    @Test func eachEventIsReservedAndClaimedInItsOwnSource() async {
        let other = String(repeating: "ab", count: 16)
        let backend = FakeBackend()
        backend.events = [Self.event("a"), Self.event("b")]
        backend.sources = ["b": other]
        backend.reservable = ["a", "b"]
        let relay = NotificationRelay(backend: backend) { _ in true }
        #expect(await relay.poll() == [.claimed("a"), .claimed("b")])
        #expect(backend.calls == ["list", "reserve legacy-t3 a", "claim legacy-t3 a r-a", "reserve \(other) b", "claim \(other) b r-b"])
        #expect(PendingNotification.validSourceId("legacy-t3"))
        #expect(PendingNotification.validSourceId(other))
        for bad in ["", "LEGACY-T3", String(repeating: "A", count: 32), String(repeating: "a", count: 31), "../x"] {
            #expect(!PendingNotification.validSourceId(bad), "\(bad)")
        }
    }

    @Test func aReleasedEventIsDeliveredOnALaterPass() async {
        let backend = FakeBackend()
        backend.events = [Self.event("a")]
        backend.reservable = ["a"]
        var accept = false
        let relay = NotificationRelay(backend: backend) { _ in accept }
        #expect(await relay.poll() == [.released("a")])
        accept = true
        #expect(await relay.poll() == [.claimed("a")])
        #expect(await relay.poll() == [], "A confirmed claim is never resent")
    }

    @Test func aTransportErrorEndsThePassWithoutSending() async {
        let backend = FakeBackend()
        backend.events = [Self.event("a")]
        backend.reservable = ["a"]
        backend.failReserve = true
        var posted = 0
        let relay = NotificationRelay(backend: backend) { _ in posted += 1; return true }
        #expect(await relay.poll() == [])
        #expect(posted == 0)
        #expect(!relay.busy)
    }

    @Test func theSourceEnvelopeDecodesWithAndWithoutLinks() throws {
        let body = """
        {"version":1,"events":[{"sourceId":"legacy-t3","event":{"id":"\(String(repeating: "1", count: 64))","kind":"failed",
         "threadId":"t","projectId":"p","threadTitle":"Build","projectTitle":"Nagi","occurredAt":"2026-11-13T00:00:00Z",
         "links":{"desktop":"t3code://threads/e/t","web":"https://app.t3.codes/threads/e/t"}}},
         {"sourceId":"\(String(repeating: "c", count: 32))","event":{"id":"\(String(repeating: "2", count: 64))","kind":"stuck",
         "threadId":"u","projectId":"p","threadTitle":"Run","projectTitle":"Nagi","occurredAt":"2026-11-13T00:00:01Z","links":null}}]}
        """
        struct Envelope: Decodable { let version: Int; let events: [PendingNotification] }
        let value = try JSONDecoder().decode(Envelope.self, from: Data(body.utf8))
        #expect(value.events.map(\.sourceId) == ["legacy-t3", String(repeating: "c", count: 32)])
        #expect(value.events[0].event.links?.desktop == "t3code://threads/e/t")
        #expect(value.events[1].event.links == nil)
    }

    @Test func bannerCopyMatchesLinux() {
        #expect(Self.event("a").bannerTitle == "Nagi · Build")
        #expect(Self.event("a").bannerBody == "Thread failed.")
        #expect(Self.event("a", "stuck").bannerBody == "Thread has been inactive.")
    }
}

@Suite struct PanelPlacement {
    @Test func messagesMatchTheLinuxShell() {
        #expect(PanelGeometry.message("ready") == .ready)
        #expect(PanelGeometry.message("close") == .close)
        #expect(PanelGeometry.message("height:512") == .height(512))
        #expect(PanelGeometry.message("height:99") == .height(320))
        #expect(PanelGeometry.message("height:9999") == .height(690))
        for value in ["height:0", "height:5", "height:-1", "height:12345", "height:abc", "Ready", ""] {
            #expect(PanelGeometry.message(value) == nil, "\(value)")
        }
    }

    @Test func macDensityIsARealZoomOfTheLinuxLayout() {
        #expect(PanelGeometry.width == 340)
        #expect(PanelGeometry.minHeight == 272)
        #expect(PanelGeometry.maxHeight == 587)
        #expect(PanelGeometry.points(css: 690) == 587)
        #expect(PanelGeometry.points(css: 512) == 436)
        #expect(PanelGeometry.points(css: 100) == 272)
        // 15 px titles and 13 px meta land near macOS menu and secondary text.
        #expect(abs(15 * PanelGeometry.zoom - 13) < 0.3)
        #expect(abs(44 * PanelGeometry.zoom - 37) < 0.5)
    }

    @Test func underTheItemInsideTheScreen() {
        let visible = CGRect(x: 0, y: 0, width: 1470, height: 919)  // 956 pt screen, 37 pt menu bar
        let item = CGRect(x: 1200, y: 919, width: 40, height: 37)
        #expect(PanelGeometry.frame(item: item, visible: visible, height: 587) == CGRect(x: 1122, y: 328, width: 340, height: 587))
        let left = CGRect(x: 100, y: 919, width: 40, height: 37)
        #expect(PanelGeometry.frame(item: left, visible: visible, height: 436) == CGRect(x: 100, y: 479, width: 340, height: 436))
        let short = CGRect(x: 0, y: 0, width: 1470, height: 500)
        #expect(PanelGeometry.frame(item: CGRect(x: 0, y: 500, width: 40, height: 24), visible: short, height: 587)
                == CGRect(x: 8, y: 8, width: 340, height: 488))
    }
}

@MainActor @Suite struct LowLimitNotifications {
    static func event() throws -> NotificationEvent {
        let body = """
        {"id":"\(String(repeating: "a", count: 64))","kind":"low_limit","provider":"codex",
         "accountId":"account","accountLabel":"Codex 1","windowId":"primary","windowLabel":"Session",
         "remainingPercent":8,"resetsAt":"2026-11-16T14:58:00Z","occurredAt":"2026-11-13T12:00:00Z",
         "links":{"desktop":null,"web":null}}
        """
        return try JSONDecoder().decode(NotificationEvent.self, from: Data(body.utf8))
    }

    @Test func decodesCopiesAndRoundTripsWithoutAThreadLink() throws {
        let event = try Self.event()
        #expect(event.opensPanel)
        #expect(event.links?.desktop == nil)
        #expect(event.bannerTitle == "Codex 1 · 8% left")
        #expect(event.bannerBody.hasPrefix("resets Mon "))
        #expect(try JSONDecoder().decode(NotificationEvent.self, from: JSONEncoder().encode(event)) == event)
    }

    @Test func cursorLimitsDecodeAndOpenOnlyThePanel() throws {
        let data = try JSONEncoder().encode(Self.event())
        let cursor = String(decoding: data, as: UTF8.self)
            .replacingOccurrences(of: "codex", with: "cursor")
            .replacingOccurrences(of: "Codex 1", with: "Cursor 1")
        let event = try JSONDecoder().decode(NotificationEvent.self, from: Data(cursor.utf8))
        #expect(event.provider == "cursor")
        #expect(event.bannerTitle == "Cursor 1 · 8% left")
        #expect(event.opensPanel && event.links?.desktop == nil && event.links?.web == nil)
    }

    @Test func aMicrosecondOffsetResetStillDecodes() throws {
        let body = """
        {"id":"\(String(repeating: "b", count: 64))","kind":"low_limit","provider":"claude",
         "accountId":"claude-1","accountLabel":"Claude 1","windowId":"five_hour","windowLabel":"Session",
         "remainingPercent":7,"resetsAt":"2026-11-16T14:58:00.123456+00:00","occurredAt":"2026-11-13T12:00:00.654321+00:00",
         "links":{"desktop":null,"web":null}}
        """
        let event = try JSONDecoder().decode(NotificationEvent.self, from: Data(body.utf8))
        #expect(event.bannerTitle == "Claude 1 · 7% left")
        #expect(event.bannerBody.hasPrefix("resets Mon "))
    }

    @Test func lowLimitsUseTheSameReserveClaimAndReleaseFlow() async throws {
        let event = try Self.event()
        let backend = FakeBackend()
        backend.events = [event]; backend.reservable = [event.id]
        var accepted = false
        let relay = NotificationRelay(backend: backend) { item in
            #expect(item.opensPanel)
            return accepted
        }
        #expect(await relay.poll() == [.released(event.id)])
        accepted = true
        #expect(await relay.poll() == [.claimed(event.id)])
        #expect(await relay.poll().isEmpty)
    }

    @Test func malformedLowLimitsNeverDecode() throws {
        let data = try JSONEncoder().encode(Self.event())
        let base = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        for bad in [-1, 101] {
            var value = base; value["remainingPercent"] = bad
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(NotificationEvent.self, from: JSONSerialization.data(withJSONObject: value))
            }
        }
    }
}
