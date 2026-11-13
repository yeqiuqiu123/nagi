"""Pure logical panel geometry and conservative EWMH right-edge reservation.

GDK values stay logical. Only the final X11 CARDINAL values are scaled.
"""
from dataclasses import dataclass
from panel_preferences import MIN_WIDTH, MAX_WIDTH


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def intersects(self, other):
        return (self.x < other.right and other.x < self.right
                and self.y < other.bottom and other.y < self.bottom)


def right_third(monitor, workarea):
    """Use the available area, including existing top/side docks; never enlarge it."""
    x, y = max(monitor.x, workarea.x), max(monitor.y, workarea.y)
    right, bottom = min(monitor.right, workarea.right), min(monitor.bottom, workarea.bottom)
    if right <= x or bottom <= y:
        raise ValueError('No usable monitor work area')
    width = (right - x + 2) // 3
    return Rect(right - width, y, width, bottom - y)


def sized_panel(monitor, workarea, preference):
    """Clamp without mutating the preference; use only the unreserved work area."""
    area = right_third(monitor, workarea)
    available = area.right - max(monitor.x, workarea.x)
    if available < MIN_WIDTH or area.height < 240:
        raise ValueError('Work area too small for a readable panel')
    preferred = preference.width
    if preference.preset == 'compact':
        preferred = 640
    elif preference.preset == 'medium':
        preferred = 960
    elif preference.preset == 'large':
        preferred = area.width
    width = min(available, MAX_WIDTH, max(MIN_WIDTH, preferred))
    return Rect(area.right - width, area.y, width, area.height)


def pointer_sized_panel(initial, monitor, workarea, press_x, pointer_x):
    """Logical root-pointer delta, independent of the moving west-edge origin."""
    if type(press_x) is not int or type(pointer_x) is not int:
        raise ValueError('Logical pointer coordinates unavailable')
    left, top = max(monitor.x, workarea.x), max(monitor.y, workarea.y)
    right, bottom = min(monitor.right, workarea.right), min(monitor.bottom, workarea.bottom)
    if (right - left < MIN_WIDTH or bottom - top < 240
            or initial.right != right or initial.y != top or initial.bottom != bottom):
        raise ValueError('Resize work area unavailable')
    width = min(MAX_WIDTH, right - left, max(MIN_WIDTH, initial.width + press_x - pointer_x))
    return Rect(right - width, top, width, bottom - top)


def reserved_workarea(workarea, panel):
    """The work area expected after our own strut, not a new sizing baseline."""
    return Rect(workarea.x, workarea.y, max(0, panel.x - workarea.x), workarea.height)


def workarea_needs_refit(current, baseline, reserved, topology, previous_topology):
    """Self-strut notifications must never recursively shrink the panel."""
    return topology != previous_topology or current not in (baseline, reserved)


def right_strut(panel, monitor, monitors, scale, root_size):
    """Return the standard 12 CARDINALs, or None for unsafe/mixed-scale layouts.

    X11 struts are root-edge distances, not monitor-local widths. Interior edges
    and any strip overlapping another monitor must remain normal windows.
    monitors contains (logical Rect, integer scale) pairs; root_size is physical.
    """
    if (type(scale) is not int or scale < 1 or not monitors
            or panel.width < 320 or panel.height < 240):
        return None
    root_width, root_height = root_size
    if root_width <= 0 or root_height <= 0 or any(s != scale for _, s in monitors):
        return None
    if (min(r.x for r, _ in monitors) != 0 or min(r.y for r, _ in monitors) != 0
            or max(r.right for r, _ in monitors) * scale != root_width
            or max(r.bottom for r, _ in monitors) * scale != root_height
            or monitor.right * scale != root_width):
        return None
    if not (monitor.x <= panel.x < panel.right <= monitor.right
            and monitor.y <= panel.y < panel.bottom <= monitor.bottom):
        return None
    strip = Rect(panel.x, panel.y, root_width // scale - panel.x, panel.height)
    if any(r != monitor and r.intersects(strip) for r, _ in monitors):
        return None
    return (0, root_width - panel.x * scale, 0, 0, 0, 0,
            panel.y * scale, panel.bottom * scale - 1, 0, 0, 0, 0)
