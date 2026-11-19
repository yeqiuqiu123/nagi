import Foundation
import Testing
@testable import NagiCore

// The same table as tests/test_github_links.py (nagi_links.github_link) and safeGithub in
// tests/glance-ci.test.cjs: tests/github-link-cases.json.
@Suite struct GitHubLinkPolicy {
    /// tests/github-link-cases.json: the one table all three validators are tested against.
    static let cases: [String: [String]] = {
        let table = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("tests/github-link-cases.json")
        guard let data = try? Data(contentsOf: table),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return [:] }
        // The lists only; the table's two notes are plain strings and are left out.
        return object.compactMapValues { $0 as? [String] }
    }()
    static let accepted: [String] = cases["accepted"] ?? []
    static let refused: [String] = cases["refused"] ?? []
    static let reserved: [String] = cases["reserved"] ?? []

    @Test func theSharedTableIsThere() {
        #expect(Self.accepted.count >= 8)
        #expect(Self.refused.count >= 70)
        #expect(Self.reserved.count >= 300)
    }

    @Test func acceptedShapesAreReturnedUnchanged() {
        for value in Self.accepted { #expect(SourceLinks.githubLink(value) == value, "\(value)") }
    }

    @Test func everythingElseIsRefused() {
        for value in Self.refused { #expect(SourceLinks.githubLink(value) == nil, "\(value)") }
    }

    @Test func gitHubsOwnFirstSegmentsAreNeverAnOwner() {
        // /new/import and /features/actions have the shape of a repository; so does every
        // other page under a reserved name, whatever route follows and however it is cased.
        for name in Self.reserved {
            for owner in [name, name.uppercased(), name.capitalized] {
                for rest in ["x", "x/pull/1", "actions", "actions/actions", "x/deployments"] {
                    let link = "https://github.com/" + owner + "/" + rest
                    #expect(SourceLinks.githubLink(link) == nil, "\(link)")
                }
            }
        }
    }

    @Test func aRepositoryNameIsAName() {
        for repo in [".", "..", "r.", "r..", "...", ".github."] {
            let link = "https://github.com/o/" + repo + "/pull/1"
            #expect(SourceLinks.githubLink(link) == nil, "\(link)")
        }
        #expect(SourceLinks.githubLink("https://github.com/o/.github/pull/1") == "https://github.com/o/.github/pull/1")
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
        #expect(!SourceLinks.openLink("https://github.com/o/r/pull/1", hasDesktopHandler: { _ in true }, open: { _ in false }))
    }
}
