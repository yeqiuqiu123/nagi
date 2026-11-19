import Foundation
import Testing
@testable import NagiCore

// The same accepted and refused table as tests/test_github_links.py (nagi_links.github_link)
// and safeGithub in tests/glance-ci.test.cjs.
@Suite struct GitHubLinkPolicy {
    static let accepted = [
        "https://github.com/o/r",
        "https://github.com/o/r/pull/12",
        "https://github.com/o/r/pull/12/checks",
        "https://github.com/o/r/actions/runs/123",
        "https://github.com/o/r/commit/0123456789abcdef0123456789abcdef01234567/checks",
        "https://github.com/o/r/deployments",
        "https://github.com/tidepool-labs/tidepool.web/pull/128",
        "https://github.com/o/r/a/b/c/d/e/f",
    ]
    static let refused = [
        "http://github.com/o/r",
        "https://github.com.evil.example/o/r",
        "https://evil.example/github.com/o/r",
        "https://user@github.com/o/r",
        "https://user:secret@github.com/o/r",
        "https://github.com:443/o/r",
        "https://github.com/o/r/pull/12?tab=checks",
        "https://github.com/o/r?",
        "https://github.com/o/r#top",
        "https://github.com/o/r/pull/12#",
        "https://github.com/o/../r",
        "https://github.com/o/r/..",
        "https://github.com/o/r/./pull",
        "https://github.com/o/..",
        "https://github.com/o/r%2Fpull/1",
        "https://github.com/o/r/pull%2F1",
        "https://github.com/o/r/a/b/c/d/e/f/g",
        "https://github.com/o/r\n",
        "https://github.com/o/r/pull/1\r",
        "https://github.com/o/r/ pull",
        "https://github.com/o//r",
        "https://github.com/o/r/",
        "https://github.com//o/r",
        "https://gist.github.com/o/r",
        "https://GITHUB.com/o/r",
        "HTTPS://github.com/o/r",
        "https://github.com/o",
        "https://github.com/",
        "https://github.com",
        "https://github.com/o/r\\x",
        "https://github.com/o_x/r",
        "https://github.com/" + String(repeating: "o", count: 40) + "/r",
        "https://github.com/o/" + String(repeating: "r", count: 101),
        "https://github.com/o/r/" + String(repeating: "x", count: 201),
        "https://github.com/o/r/" + String(repeating: "a/", count: 1100) + "a",
        "https://github.com/o/r/\u{e9}",
        "javascript:alert(1)",
        "file:///tmp/x",
        "t3code://threads/e/a",
        "",
    ]

    @Test func acceptedShapesAreReturnedUnchanged() {
        for value in Self.accepted { #expect(SourceLinks.githubLink(value) == value, "\(value)") }
    }

    @Test func everythingElseIsRefused() {
        for value in Self.refused { #expect(SourceLinks.githubLink(value) == nil, "\(value)") }
    }

    @Test func openLinkKeepsThreadsFirstThenGitHubOnce() {
        var opened: [String] = []
        #expect(SourceLinks.openLink("t3code://threads/e/a%3Ab", hasDesktopHandler: { _ in false },
                                     open: { opened.append($0.absoluteString); return true }))
        #expect(opened == ["https://app.t3.codes/threads/e/a%3Ab"])
        opened = []
        #expect(SourceLinks.openLink("https://github.com/o/r/pull/12", hasDesktopHandler: { _ in true },
                                     open: { opened.append($0.absoluteString); return true }))
        #expect(opened == ["https://github.com/o/r/pull/12"])
        opened = []
        for value in Self.refused where value != "t3code://threads/e/a" {
            #expect(!SourceLinks.openLink(value, hasDesktopHandler: { _ in true },
                                          open: { opened.append($0.absoluteString); return true }), "\(value)")
        }
        #expect(opened.isEmpty)
        #expect(!SourceLinks.openLink("https://github.com/o/r", hasDesktopHandler: { _ in true }, open: { _ in false }))
    }
}
