import textwrap
import pytest
from pathlib import Path

from config import Config, save_mode


@pytest.fixture
def cfg_file(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(textwrap.dedent("""\
        [claude]
        cookies = abc
        org_id  = xyz
        poll_interval = 60

        [ui]
        language = ko
        mode     = overlay         ; overlay | tray | cli | autohide

        [tray]
        popup_position = above

        [autohide]
        edge = right
        peek_pixels = 3
        slide_ms = 150
        hide_delay_ms = 1500
    """), encoding="utf-8")
    return p


def test_load_basic_values(cfg_file):
    cfg = Config.load(cfg_file)
    assert cfg.cookies == "abc"
    assert cfg.org_id == "xyz"
    assert cfg.poll_interval == 60
    assert cfg.language == "ko"
    assert cfg.mode == "overlay"
    assert cfg.tray_popup_position == "above"
    assert cfg.autohide_edge == "right"
    assert cfg.autohide_peek_pixels == 3
    assert cfg.autohide_slide_ms == 150
    assert cfg.autohide_hide_delay_ms == 1500


def test_mode_fallback_when_missing(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n", encoding="utf-8")
    cfg = Config.load(p)
    assert cfg.mode == "overlay"


def test_mode_falls_back_on_invalid_value(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = bogus\n", encoding="utf-8")
    cfg = Config.load(p)
    assert cfg.mode == "overlay"


def test_save_mode_preserves_comments(cfg_file):
    save_mode(cfg_file, "tray")
    text = cfg_file.read_text(encoding="utf-8")
    # The value changed
    assert "mode     = tray" in text or "mode = tray" in text
    # The comment after the value is preserved
    assert "; overlay | tray | cli | autohide" in text
    # Other keys untouched
    assert "language = ko" in text


def test_save_mode_adds_section_if_missing(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n", encoding="utf-8")
    save_mode(p, "tray")
    text = p.read_text(encoding="utf-8")
    assert "[ui]" in text
    assert "mode = tray" in text
