"""Background polling thread; calls back into the consumer on each successful fetch."""

import threading


class Poller:
    def __init__(self, client, interval: float, on_data):
        self.client = client
        self.interval = interval
        self.on_data = on_data
        self._stop = threading.Event()
        self._trigger_evt = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._trigger_evt.set()
        if self._thread:
            self._thread.join(timeout=2)

    def trigger(self):
        """Force an immediate fetch on the poller thread."""
        self._trigger_evt.set()

    def _loop(self):
        while not self._stop.is_set():
            data = self.client.fetch()
            if data is not None:
                try:
                    self.on_data(data)
                except Exception as e:
                    print(f"[poller callback error] {e}")
            # Wait interval OR until triggered/stopped, whichever comes first
            self._trigger_evt.wait(timeout=self.interval)
            self._trigger_evt.clear()
