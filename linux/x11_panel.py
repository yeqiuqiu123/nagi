"""Original, bounded libX11 binding for this app's EWMH properties and bounded own-frame reads.

No Python Xlib dependency, root writes, window enumeration or input operations.
Standard: https://specifications.freedesktop.org/wm/latest/ar01s05.html
Importing is pure; connecting is an explicit native-runtime action.
"""
import ctypes as C
from ctypes.util import find_library


STRUTS = ('_NET_WM_STRUT_PARTIAL', '_NET_WM_STRUT')
REQUIRED = ('_NET_WM_WINDOW_TYPE', '_NET_WM_WINDOW_TYPE_DOCK', *STRUTS)


class XConnection:
    def __init__(self):
        name = find_library('X11')
        if not name:
            raise OSError('libX11 unavailable')
        self.lib = lib = C.CDLL(name)
        signatures = {
            'XOpenDisplay': ([C.c_char_p], C.c_void_p),
            'XDefaultRootWindow': ([C.c_void_p], C.c_ulong),
            'XDefaultScreen': ([C.c_void_p], C.c_int),
            'XDisplayWidth': ([C.c_void_p, C.c_int], C.c_int),
            'XDisplayHeight': ([C.c_void_p, C.c_int], C.c_int),
            'XInternAtom': ([C.c_void_p, C.c_char_p, C.c_int], C.c_ulong),
            'XChangeProperty': ([C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong,
                                 C.c_int, C.c_int, C.c_void_p, C.c_int], C.c_int),
            'XDeleteProperty': ([C.c_void_p, C.c_ulong, C.c_ulong], C.c_int),
            'XGetWindowProperty': ([C.c_void_p, C.c_ulong, C.c_ulong, C.c_long,
                                   C.c_long, C.c_int, C.c_ulong, C.POINTER(C.c_ulong),
                                   C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                                   C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)], C.c_int),
            'XQueryTree': ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                            C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)], C.c_int),
            'XGetGeometry': ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                              C.POINTER(C.c_int), C.POINTER(C.c_uint), C.POINTER(C.c_uint),
                              C.POINTER(C.c_uint), C.POINTER(C.c_uint)], C.c_int),
            'XTranslateCoordinates': ([C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int,
                                       C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_ulong)], C.c_int),
            'XFree': ([C.c_void_p], C.c_int),
            'XFlush': ([C.c_void_p], C.c_int),
            'XCloseDisplay': ([C.c_void_p], C.c_int),
        }
        for symbol, (args, result) in signatures.items():
            fn = getattr(lib, symbol)
            fn.argtypes, fn.restype = args, result
        self.display = lib.XOpenDisplay(None)
        if not self.display:
            raise OSError('X11 display unavailable')
        self.root = lib.XDefaultRootWindow(self.display)
        screen = lib.XDefaultScreen(self.display)
        self.root_size = (lib.XDisplayWidth(self.display, screen), lib.XDisplayHeight(self.display, screen))

    def atom(self, name):
        return self.lib.XInternAtom(self.display, name.encode('ascii'), False)

    def read(self, window, name, kind):
        actual, count, rest = C.c_ulong(), C.c_ulong(), C.c_ulong()
        fmt, ptr = C.c_int(), C.c_void_p()
        status = self.lib.XGetWindowProperty(self.display, window, self.atom(name), 0, 4096,
                                             False, self.atom(kind), C.byref(actual),
                                             C.byref(fmt), C.byref(count), C.byref(rest), C.byref(ptr))
        try:
            if status or actual.value != self.atom(kind) or fmt.value != 32 or rest.value or count.value > 4096:
                return ()
            return tuple(C.cast(ptr, C.POINTER(C.c_ulong))[i] for i in range(count.value)) if ptr.value else ()
        finally:
            if ptr.value:
                self.lib.XFree(ptr)

    def frame_geometry(self, xid):
        """Read this owned client's actual outer ancestor, never cached WM hints.

        GNOME can retain a NORMAL window's _NET_FRAME_EXTENTS after it becomes
        an unframed DOCK. Query only this XID and at most three own ancestors;
        no window enumeration, property writes or geometry requests.
        """
        if type(xid) is not int or xid <= 0 or xid == self.root:
            raise ValueError('Owned application XID required')
        chain = []
        for _ in range(4):
            if xid in [item[0] for item in chain]:
                raise OSError('Cyclic frame ancestry')
            root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
            children = C.POINTER(C.c_ulong)()
            try:
                ok = self.lib.XQueryTree(self.display, xid, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
            finally:
                if children:
                    self.lib.XFree(C.cast(children, C.c_void_p))
            if not ok or root.value != self.root or parent.value == 0 or count.value > 4096:
                raise OSError('Frame ancestry unavailable')
            chain.append((xid, parent.value))
            if parent.value == self.root:
                break
            xid = parent.value
        else:
            raise OSError('Frame ancestry too deep')
        x, y, rx, ry = C.c_int(), C.c_int(), C.c_int(), C.c_int()
        width, height, border, depth, root, child = C.c_uint(), C.c_uint(), C.c_uint(), C.c_uint(), C.c_ulong(), C.c_ulong()
        if (not self.lib.XGetGeometry(self.display, xid, C.byref(root), C.byref(x), C.byref(y), C.byref(width), C.byref(height), C.byref(border), C.byref(depth))
                or root.value != self.root or not width.value or not height.value or border.value > 16384
                or not self.lib.XTranslateCoordinates(self.display, xid, self.root, 0, 0, C.byref(rx), C.byref(ry), C.byref(child))):
            raise OSError('Frame geometry unavailable')
        # Reject a reparenting race rather than interpreting a mixed snapshot.
        for owned, expected_parent in chain:
            root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
            children = C.POINTER(C.c_ulong)()
            try:
                ok = self.lib.XQueryTree(self.display, owned, C.byref(root), C.byref(parent), C.byref(children), C.byref(count))
            finally:
                if children:
                    self.lib.XFree(C.cast(children, C.c_void_p))
            if not ok or root.value != self.root or parent.value != expected_parent or count.value > 4096:
                raise OSError('Frame ancestry changed')
        return (rx.value - border.value, ry.value - border.value,
                width.value + 2 * border.value, height.value + 2 * border.value)

    def write(self, window, name, kind, values):
        # Xlib format=32 takes native unsigned longs, even on 64-bit hosts.
        data = (C.c_ulong * len(values))(*values)
        self.lib.XChangeProperty(self.display, window, self.atom(name), self.atom(kind),
                                 32, 0, C.cast(data, C.c_void_p), len(values))

    def delete(self, window, name):
        self.lib.XDeleteProperty(self.display, window, self.atom(name))

    def flush(self):
        self.lib.XFlush(self.display)

    def close(self):
        if self.display:
            self.lib.XCloseDisplay(self.display)
            self.display = None


class PanelReservation:
    """Own one live application's XID. Clear while it still exists, before destroy."""
    def __init__(self, connection, xid):
        if type(xid) is not int or xid <= 0 or xid == connection.root:
            raise ValueError('An application XID is required')
        self.connection, self.xid, self.active = connection, xid, False

    def supported(self):
        c = self.connection
        supported = c.read(c.root, '_NET_SUPPORTED', 'ATOM')
        return all(c.atom(name) in supported for name in REQUIRED)

    def apply(self, strut):
        if (len(strut) != 12 or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in strut)
                or not self.supported()):
            return False
        c = self.connection
        c.write(self.xid, '_NET_WM_WINDOW_TYPE', 'ATOM', [c.atom('_NET_WM_WINDOW_TYPE_DOCK')])
        c.write(self.xid, STRUTS[0], 'CARDINAL', strut)
        c.write(self.xid, STRUTS[1], 'CARDINAL', strut[:4])
        c.flush()
        self.active = True
        return True

    def clear(self):
        c = self.connection
        for name in STRUTS:
            c.delete(self.xid, name)
        c.write(self.xid, '_NET_WM_WINDOW_TYPE', 'ATOM', [c.atom('_NET_WM_WINDOW_TYPE_NORMAL')])
        c.flush()
        self.active = False
