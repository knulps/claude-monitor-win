import threading
import time

from poller import Poller


class FakeClient:
    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return self.sequence.pop(0) if self.sequence else None


def test_poller_fires_callback_on_success():
    client = FakeClient(["d1", "d2"])
    received = []
    p = Poller(client, interval=0.05, on_data=received.append)
    p.start()
    time.sleep(0.18)
    p.stop()
    assert "d1" in received
    assert "d2" in received


def test_poller_skips_callback_on_none():
    client = FakeClient([None, "d1"])
    received = []
    p = Poller(client, interval=0.05, on_data=received.append)
    p.start()
    time.sleep(0.18)
    p.stop()
    assert received == ["d1"]


def test_trigger_runs_immediately_off_thread():
    client = FakeClient(["d1", "d2"])
    received = []
    p = Poller(client, interval=999, on_data=received.append)
    p.start()
    p.trigger()
    time.sleep(0.1)
    p.stop()
    assert received == ["d1"]
