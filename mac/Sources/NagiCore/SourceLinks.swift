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

    /// First segments that are GitHub's own pages and can never be an account: sign-in, SSO,
    /// settings, /new, /features and the rest. Source: Mottie/github-reserved-names 2.2.0 (MIT), https://github.com/Mottie/github-reserved-names, plus GitHub's sign-in and SSO segments.
    /// The same text is in nagi_links.py and web/glance-ci.js.
    private static let githubReserved: Set<String> = Set((
        "300 302 400 401 402 403 404 405 406 407 408 409 410 411 412 413 414 415 416 417 418 419 420 421 422 423 424 425 426 427 428 429 430 431 500 501 502 503 504 505 506 507 508 509 510 511 693 694 695 900 about account admin advisories anonymous any api apps attributes auth billing blob blog bounty branches business businesses c cache careers case-studies categories central certification changelog chat cla cloud codereview codespaces collection collections comments commit commits companies compare contact contributing cookbook copilot coupons customer customer-stories customers dashboard dashboard-feed dashboards design develop developer diff discover discussions downloads downtime editor editors edu education enterprise enterprises events explore featured features feed files fixtures forked garage ghost gist gists git-guides github github-copilot graphs groups guide guides help help-wanted home hooks hosting hovercards identity images inbox individual info integration interfaces introduction invalid-email-address investors issues jobs join journal journals lab labs languages launch layouts learn legal library linux listings lists login logos logout mac maintenance malware man marketplace mcp mention mentioned mentioning mentions migrating milestones mine mirrors mobile navigation network new news newsletter newsroom none nonprofit nonprofits notices notifications oauth offer open-source organisations organizations orgs pages partners password-reset payments personal plans plugins popular popularity posts press preview pricing professional projects pulls raw readme recommendations redeem releases render reply repos repositories resources restore revert save-net-neutrality saved scraping search security services session sessions settings shareholders showcases signin signup site site-policy sitemap social-impact socials spam sponsors ssh sso staff starred stars static status statuses storage store stories styleguide subscriptions suggest suggestion suggestions support suspended talks teach teacher teachers teaching team teams ten terms timeline topic topics tos tour train training translations tree trending two-factor undefined updates user-attachments username users visualization w watching why-github wiki wikis windows works-with www0 www1 www2 www3 www4 www5 www6 www7 www8 www9"
    ).split(separator: " ").map(String.init))

    /// A port of nagi_links.github_link (and safeGithub in web/glance-ci.js):
    /// https://github.com/<owner>/<repo>/ followed by one of the routes the panel links to
    /// (pull/<n>, actions, actions/runs/<n>, deployments), returned unchanged.
    /// No credentials, port, query, fragment, percent sign or empty segment; no reserved
    /// first segment; no repository named `.` or `..` or ending in a dot; no other route,
    /// and not the bare /owner/repo.
    public static func githubLink(_ value: String) -> String? {
        let prefix = "https://github.com/"
        guard value.unicodeScalars.count <= 2048, !value.unicodeScalars.contains(where: { $0.value < 33 }),
              !value.unicodeScalars.contains(where: { "%?#\\@".unicodeScalars.contains($0) }),
              value.hasPrefix(prefix) else { return nil }
        let parts = value.dropFirst(prefix.count).split(separator: "/", maxSplits: 2, omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 3,
              matches(parts[0], "\\A[A-Za-z0-9-]{1,39}\\z"),
              matches(parts[1], "\\A[A-Za-z0-9._-]{1,100}\\z"),
              !githubReserved.contains(parts[0].lowercased()),
              !parts[1].hasSuffix("."),
              matches(parts[2], "\\A(?:pull/[1-9][0-9]{0,18}|actions(?:/runs/[1-9][0-9]{0,18})?|deployments)\\z") else { return nil }
        return prefix + parts.joined(separator: "/")
    }

    /// A thread link as openThread does, else a GitHub link in the browser (nagi_links.open_link).
    public static func openLink(_ value: String, hasDesktopHandler: (URL) -> Bool, open: (URL) -> Bool) -> Bool {
        if openThread(value, hasDesktopHandler: hasDesktopHandler, open: open) { return true }
        guard let link = githubLink(value), let url = URL(string: link) else { return false }
        return open(url)
    }
}
