import Foundation
import Testing
@testable import NagiCore

// A link leaves the panel only on the owner's own click or Return (GlancePanel's navigation
// policy). A page-made activation has no event behind it and is refused.
@Suite struct ActivationGatePolicy {
    @Test func aRealEventVouchesForItsNavigation() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        #expect(gate.consume(at: 100.02))
    }

    @Test func aSyntheticActivationHasNoEventBehindIt() {
        var gate = ActivationGate()
        #expect(!gate.consume(at: 100.0))
    }

    @Test func oneEventVouchesForOneNavigationOnly() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        #expect(gate.consume(at: 100.01))
        // A script that follows the owner's click with a second link gets nothing.
        #expect(!gate.consume(at: 100.02))
    }

    @Test func aStaleEventDoesNotCount() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        #expect(!gate.consume(at: 100.0 + ActivationGate.window + 0.01))
        // Refusing uses the event up too: it can't be tried again a moment later.
        #expect(!gate.consume(at: 100.5))
    }

    @Test func anEventFromTheFutureDoesNotCount() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        #expect(!gate.consume(at: 99.9))
    }

    @Test func theNewestEventIsTheOneThatCounts() {
        var gate = ActivationGate()
        gate.record(at: 10.0)
        gate.record(at: 100.0)
        #expect(gate.consume(at: 100.9))
    }

    @Test func onlyReturnAndEnterActivateALink() {
        #expect(ActivationGate.activates(keyCode: 36))
        #expect(ActivationGate.activates(keyCode: 76))
        for code: UInt16 in [49, 53, 48, 0, 125] { #expect(!ActivationGate.activates(keyCode: code)) }
    }
}
