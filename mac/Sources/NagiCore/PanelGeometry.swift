import Foundation
import CoreGraphics

/// The page's only native messages: `ready`, `close` and `height:<px>`.
public enum PanelMessage: Equatable, Sendable {
    case ready
    case close
    case height(Double)
}

/// Where the glance sits: 4 pt under the menu bar, its left edge on the status item like
/// Apple's own extras, at least 8 pt inside the visible screen.
///
/// The page is laid out at 400 × 320–690 CSS px (the Linux panel). On the Mac it is shown
/// at `zoom` 0.85 by real relayout (WKWebView.pageZoom), never a bitmap scale, so the
/// panel is 340 pt wide and thread titles render at about 13 pt, like menu text.
public enum PanelGeometry {
    public static let cssWidth: Double = 400
    public static let cssMinHeight: Double = 320
    public static let cssMaxHeight: Double = 690
    public static let zoom: Double = 0.85
    public static let width: Double = cssWidth * zoom
    public static let minHeight: Double = (cssMinHeight * zoom).rounded()
    public static let maxHeight: Double = (cssMaxHeight * zoom).rounded()
    public static let barGap: Double = 4
    public static let screenEdge: Double = 8
    public static let cornerRadius: Double = 10

    public static func clampHeight(_ value: Double) -> Double {
        Swift.max(minHeight, Swift.min(maxHeight, value))
    }

    /// The page's reported CSS height as whole panel points.
    public static func points(css value: Double) -> Double {
        clampHeight((Swift.max(cssMinHeight, Swift.min(cssMaxHeight, value)) * zoom).rounded(.up))
    }

    /// A port of linux/notifications.py panel_message.
    public static func message(_ value: String) -> PanelMessage? {
        if value == "ready" { return .ready }
        if value == "close" { return .close }
        guard value.range(of: "\\Aheight:[1-9][0-9]{1,3}\\z", options: .regularExpression) != nil,
              let pixels = Double(value.dropFirst("height:".count)) else { return nil }
        return .height(Swift.max(cssMinHeight, Swift.min(cssMaxHeight, pixels)))
    }

    /// Frame in AppKit screen coordinates (origin bottom-left). `item` is the status
    /// item's window frame and `visible` its screen's visibleFrame.
    public static func frame(item: CGRect, visible: CGRect, height: Double) -> CGRect {
        let top = Swift.min(Double(item.minY), Double(visible.maxY)) - barGap
        let room = top - Double(visible.minY) - screenEdge
        let h = Swift.max(Swift.min(clampHeight(height), room), Swift.min(minHeight, room))
        var x = Double(item.minX)
        x = Swift.min(x, Double(visible.maxX) - screenEdge - width)
        x = Swift.max(x, Double(visible.minX) + screenEdge)
        return CGRect(x: x, y: top - h, width: width, height: h)
    }
}
