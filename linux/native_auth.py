"""Native-owned session refresh and bounded startup recovery; no JS credentials."""
import threading
import time

REFRESH_SECONDS = 12 * 60
RETRY_SECONDS = 30
UNAVAILABLE = 'Nagi’s local reader is unavailable. Start it, then try again.'


class SessionRecovery:
    def __init__(self, launch, load, error, schedule, cancel, dispatch, clock=time.monotonic):
        self.launch, self.load, self.error = launch, load, error
        self.schedule, self.cancel, self.dispatch, self.clock = schedule, cancel, dispatch, clock
        self.visible = False
        self.pending = False
        self.generation = 0
        self.timer = None
        self.deadline = 0
        self.delay = 1

    def _cancel_timer(self):
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None

    def shown(self):
        self.visible = True
        self.request()

    def hidden(self):
        self.visible = False
        self.generation += 1
        self.pending = False
        self._cancel_timer()

    def request(self):
        if not self.visible or self.pending:
            return
        self._cancel_timer()
        self.deadline, self.delay = self.clock() + RETRY_SECONDS, 1
        self._attempt()

    def _attempt(self):
        self.timer = None
        if not self.visible or self.pending:
            return False
        self.pending = True
        generation = self.generation
        self.dispatch(self.launch, lambda url, failed: self._complete(generation, url, failed))
        return False

    def _complete(self, generation, url, failed):
        if generation != self.generation or not self.visible:
            return False
        self.pending = False
        if not failed:
            self.load(url)
            self.timer = self.schedule(REFRESH_SECONDS, self._refresh)
        else:
            remaining = self.deadline - self.clock()
            if remaining > 0:
                self.timer = self.schedule(min(self.delay, remaining), self._attempt)
                self.delay = min(self.delay * 2, 8)
            else:
                self.error(UNAVAILABLE)
        return False

    def _refresh(self):
        self.timer = None
        self.request()
        return False


def gtk_recovery(GLib, launch, load, error):
    def dispatch(work, completed):
        def run():
            try:
                result, failed = work(), False
            except (OSError, ValueError, TypeError, KeyError):
                result, failed = None, True
            GLib.idle_add(completed, result, failed)
        threading.Thread(target=run, daemon=True).start()
    return SessionRecovery(launch, load, error,
        lambda delay, callback: GLib.timeout_add(max(1, int(delay * 1000)), callback),
        GLib.source_remove, dispatch)


def bind_auth_signal(web, trusted, refresh):
    manager = web.get_user_content_manager()
    def received(_manager, result):
        try:
            value = result.get_js_value()
            if trusted(web.get_uri()) and value.is_string() and value.to_string() == 'reauthenticate':
                refresh()
        except (AttributeError, TypeError, ValueError):
            pass
    manager.connect('script-message-received::nagiAuth', received)
    if not manager.register_script_message_handler('nagiAuth'):
        raise ValueError('Native authentication channel unavailable')
