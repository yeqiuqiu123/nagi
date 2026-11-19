import Foundation

/// The only destinations the native shell will load or open.
public enum SourceLinks {
    /// Same-document sections of the glance (linux/notifications.py SECTIONS).
    public static let glanceSections: Set<String> = ["agents", "limits", "ended"]

    /// This computer's loopback glance page (or its /overview alias), nothing else.
    public static func privateURL(_ url: URL, sameOriginAs page: URL) -> Bool {
        guard page.scheme == "http", page.host == "127.0.0.1",
              let port = page.port, (1024...65535).contains(port),
              url.scheme == "http", url.host == "127.0.0.1", url.port == port,
              url.user == nil, url.password == nil, url.query == nil,
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              ["/glance", "/overview"].contains(components.percentEncodedPath) else { return false }
        guard let fragment = url.fragment else { return true }
        return glanceSections.contains(fragment)
    }

    public struct ThreadLinks: Equatable, Sendable {
        public let desktop: String
        public let web: String
    }

    private static let unreserved = CharacterSet(charactersIn:
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~")

    /// A port of nagi_links.thread_links: a generated T3 thread link (desktop or web),
    /// canonicalised to both forms. Opaque, percent-encoded IDs; anything else is nil.
    public static func threadLinks(_ value: String) -> ThreadLinks? {
        let scalars = value.unicodeScalars
        guard scalars.count <= 4096, !scalars.contains(where: { $0.value < 33 }),
              let separator = value.range(of: "://") else { return nil }
        let scheme = value[..<separator.lowerBound].lowercased()
        let rest = String(value[separator.upperBound...])
        let tail: String
        if scheme == "t3code", rest.hasPrefix("threads/") {
            tail = String(rest.dropFirst("threads/".count))
        } else if scheme == "https", rest.hasPrefix("app.t3.codes/threads/") {
            tail = String(rest.dropFirst("app.t3.codes/threads/".count))
        } else {
            return nil
        }
        let parts = tail.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 2 else { return nil }
        var encoded: [String] = []
        for part in parts {
            guard part.range(of: "\\A[A-Za-z0-9_.~%-]+\\z", options: .regularExpression) != nil,
                  part.range(of: "%(?![0-9a-fA-F]{2})", options: .regularExpression) == nil,
                  let decoded = part.removingPercentEncoding,
                  !decoded.isEmpty, decoded != ".", decoded != "..",
                  decoded.unicodeScalars.count <= 512,
                  !decoded.unicodeScalars.contains(where: { $0.value < 33 }),
                  let canonical = decoded.addingPercentEncoding(withAllowedCharacters: unreserved) else { return nil }
            encoded.append(canonical)
        }
        let path = encoded.joined(separator: "/")
        return ThreadLinks(desktop: "t3code://threads/" + path, web: "https://app.t3.codes/threads/" + path)
    }

    /// Desktop link first when a handler exists, then the web fallback (nagi_links.open_thread).
    public static func openThread(_ value: String, hasDesktopHandler: (URL) -> Bool, open: (URL) -> Bool) -> Bool {
        guard let links = threadLinks(value),
              let desktop = URL(string: links.desktop), let web = URL(string: links.web) else { return false }
        if hasDesktopHandler(desktop), open(desktop) { return true }
        return open(web)
    }

    private static func matches(_ value: String, _ pattern: String) -> Bool {
        value.range(of: pattern, options: .regularExpression) != nil
    }

    /// A port of nagi_links.github_link (and safeGithub in web/glance-ci.js): a plain
    /// https://github.com/<owner>/<repo> link plus 0 to 6 more segments, returned unchanged.
    /// No credentials, port, query, fragment, percent sign, `.`/`..` or empty segment.
    public static func githubLink(_ value: String) -> String? {
        let prefix = "https://github.com/"
        guard value.unicodeScalars.count <= 2048, !value.unicodeScalars.contains(where: { $0.value < 33 }),
              !value.unicodeScalars.contains(where: { "%?#\\@".unicodeScalars.contains($0) }),
              value.hasPrefix(prefix) else { return nil }
        let parts = value.dropFirst(prefix.count).split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard (2...8).contains(parts.count),
              matches(parts[0], "\\A[A-Za-z0-9-]{1,39}\\z"),
              matches(parts[1], "\\A[A-Za-z0-9._-]{1,100}\\z"),
              parts.dropFirst(2).allSatisfy({ matches($0, "\\A[A-Za-z0-9._-]{1,200}\\z") }),
              !parts.contains(where: { $0 == "." || $0 == ".." }) else { return nil }
        return prefix + parts.joined(separator: "/")
    }

    /// A thread link as openThread does, else a GitHub link in the browser (nagi_links.open_link).
    public static func openLink(_ value: String, hasDesktopHandler: (URL) -> Bool, open: (URL) -> Bool) -> Bool {
        if openThread(value, hasDesktopHandler: hasDesktopHandler, open: open) { return true }
        guard let link = githubLink(value), let url = URL(string: link) else { return false }
        return open(url)
    }
}
