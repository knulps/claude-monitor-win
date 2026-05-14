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
