import Foundation
import Testing
@testable import NagiCore

// A link leaves the panel only on the owner's own click or Return (GlancePanel's navigation
// policy). A page-made activation has no event behind it and is refused.
@Suite struct ActivationGatePolicy {
    @Test func aRealEventVouchesForItsNavigation() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        let used1 = gate.consume(at: 100.02)
        #expect(used1)
    }

    @Test func aSyntheticActivationHasNoEventBehindIt() {
        var gate = ActivationGate()
        let used2 = gate.consume(at: 100.0)
        #expect(!used2)
    }

    @Test func oneEventVouchesForOneNavigationOnly() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        let used3 = gate.consume(at: 100.01)
        #expect(used3)
        // A script that follows the owner's click with a second link gets nothing.
        let used4 = gate.consume(at: 100.02)
        #expect(!used4)
    }

    @Test func aStaleEventDoesNotCount() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        let used5 = gate.consume(at: 100.0 + ActivationGate.window + 0.01)
        #expect(!used5)
        // Refusing uses the event up too: it can't be tried again a moment later.
        let used6 = gate.consume(at: 100.5)
        #expect(!used6)
    }

    @Test func anEventFromTheFutureDoesNotCount() {
        var gate = ActivationGate()
        gate.record(at: 100.0)
        let used7 = gate.consume(at: 99.9)
        #expect(!used7)
    }

    @Test func theNewestEventIsTheOneThatCounts() {
        var gate = ActivationGate()
        gate.record(at: 10.0)
        gate.record(at: 100.0)
        let used8 = gate.consume(at: 100.9)
        #expect(used8)
    }

    @Test func onlyReturnAndEnterActivateALink() {
        #expect(ActivationGate.activates(keyCode: 36))
        #expect(ActivationGate.activates(keyCode: 76))
        for code: UInt16 in [49, 53, 48, 0, 125] { #expect(!ActivationGate.activates(keyCode: code)) }
    }
}
