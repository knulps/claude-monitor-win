from pathlib import Path

from mode_manager import ModeManager


class FakeView:
    def __init__(self, manager):
        self.manager = manager
        self.started = False
        self.stopped = False
        self.updates = []
        self.initial = None

    def start(self, initial):
        self.started = True
        self.initial = initial

    def stop(self):
        self.stopped = True

    def on_update(self, data):
        self.updates.append(data)


class FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))


class FakeTkView(FakeView):
    """A FakeView that mimics a Tk-based view: it has a `root` attribute."""

    def __init__(self, manager):
        super().__init__(manager)
        self.root = FakeRoot()

    def stop(self):
        super().stop()
        self.root = None


def test_initial_view_is_started_and_seeded(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    assert mgr.current_view.started
    assert mgr.current_mode == "overlay"


def test_data_callback_caches_and_dispatches(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    mgr.on_poll_data("DATA")
    assert mgr.current_view.updates == ["DATA"]
    assert mgr.last_data == "DATA"


def test_switch_stops_old_starts_new_with_cache(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    mgr.on_poll_data("D1")
    old = mgr.current_view
    mgr._do_switch("tray")
    assert old.stopped
    assert mgr.current_view is not old
    assert mgr.current_view.started
    assert mgr.current_view.initial == "D1"
    assert mgr.current_mode == "tray"


def test_save_mode_writes_to_config(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    mgr._do_switch("tray")
    assert "mode = tray" in cfg.read_text(encoding="utf-8")


def test_no_save_mode_skips_writing(tmp_path):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=False,
    )
    mgr.start_initial("overlay")
    mgr._do_switch("tray")
    assert "mode = overlay" in cfg.read_text(encoding="utf-8")


def test_on_poll_data_marshals_tk_view_via_after(tmp_path):
    """A Tk view (has .root) gets on_update scheduled via root.after, not called directly."""
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeTkView, "tray": FakeTkView, "cli": FakeTkView, "autohide": FakeTkView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    mgr.on_poll_data("D1")
    view = mgr.current_view
    # Not dispatched directly from the (simulated) worker thread...
    assert view.updates == []
    # ...but scheduled via root.after
    assert len(view.root.after_calls) == 1
    _ms, fn = view.root.after_calls[0]
    fn()
    assert view.updates == ["D1"]


def test_on_poll_data_skips_stale_tk_view_callback(tmp_path):
    """If the view is swapped before the after-callback runs, the callback is a no-op."""
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    mgr = ModeManager(
        cfg_path=cfg,
        view_factories={"overlay": FakeTkView, "tray": FakeTkView, "cli": FakeTkView, "autohide": FakeTkView},
        poller=None,
        save_mode=True,
    )
    mgr.start_initial("overlay")
    old = mgr.current_view
    mgr.on_poll_data("D1")
    _ms, fn = old.root.after_calls[0]
    # Switch before the scheduled callback runs
    mgr._do_switch("tray")
    fn()  # stale callback fires
    assert old.updates == []          # stale view was NOT updated


# ---------------------------------------------------------------------------
# Helper reused by Tasks 5, 6, 7, 8, 9
# ---------------------------------------------------------------------------

def _make_mgr(tmp_path, **kwargs):
    cfg = tmp_path / "c.ini"
    cfg.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    defaults = dict(
        cfg_path=cfg,
        view_factories={"overlay": FakeView, "tray": FakeView, "cli": FakeView, "autohide": FakeView},
        poller=None,
        save_mode=True,
    )
    defaults.update(kwargs)
    return ModeManager(**defaults), cfg


def test_should_show_companion_truth_table(tmp_path):
    mgr, _ = _make_mgr(tmp_path)
    cases = [
        ("overlay",  True,  True),
        ("autohide", True,  True),
        ("tray",     True,  False),
        ("cli",      True,  False),
        ("overlay",  False, False),
        ("autohide", False, False),
        ("tray",     False, False),
        ("cli",      False, False),
    ]
    for mode, flag, expected in cases:
        mgr.current_mode = mode
        mgr.tray_companion = flag
        assert mgr._should_show_companion() is expected, f"{mode=} {flag=}"


# ---------------------------------------------------------------------------
# Task 6: _sync_companion + request_toggle_companion
# ---------------------------------------------------------------------------

def test_sync_companion_starts_when_compatible(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.current_mode = "overlay"
    mgr._sync_companion()
    assert mgr.current_companion is not None
    assert mgr.current_companion.started


def test_sync_companion_skips_when_incompatible(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.current_mode = "cli"
    mgr._sync_companion()
    assert mgr.current_companion is None


def test_sync_companion_stops_existing_when_no_longer_needed(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.current_mode = "overlay"
    mgr._sync_companion()
    companion = mgr.current_companion
    mgr.tray_companion = False
    mgr._sync_companion()
    assert companion.stopped
    assert mgr.current_companion is None


def test_request_toggle_companion_persists_when_save_mode_on(tmp_path):
    saved = []
    mgr, cfg = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        save_tray_companion=lambda path, value: saved.append((path, value)),
    )
    mgr.current_mode = "overlay"
    mgr.request_toggle_companion(True)
    assert mgr.tray_companion is True
    assert saved == [(cfg, True)]


def test_request_toggle_companion_skips_save_when_no_save_mode(tmp_path):
    saved = []
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        save_mode=False,
        save_tray_companion=lambda path, value: saved.append((path, value)),
    )
    mgr.current_mode = "overlay"
    mgr.request_toggle_companion(True)
    assert mgr.tray_companion is True
    assert saved == []  # NOT persisted under --no-save-mode
