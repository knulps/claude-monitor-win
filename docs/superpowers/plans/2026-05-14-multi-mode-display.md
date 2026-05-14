# Multi-Mode Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `claude_monitor.py` into a modular, runtime-switchable display system that supports four modes (overlay, tray, cli, autohide), with the chosen mode persisted to `config.ini`.

**Architecture:** Split the monolithic `claude_monitor.py` into focused modules: a shared `Poller` + `UsageClient` data layer, a `ModeManager` that owns view lifecycle, and one View per mode under `views/`. Each Tk-based view creates and tears down its own `tk.Tk()` root on switch; the Poller persists across switches and seeds the new view with cached data.

**Tech Stack:** Python 3.8+, stdlib `tkinter` / `configparser` / `threading` / `argparse`, `curl_cffi` (existing), `pystray` + `Pillow` (new, for tray icon), `pytest` (for unit tests of pure logic).

---

## File Structure

**New files:**
- `i18n.py` — TRANSLATIONS dict + `T()` helper (extracted from current `claude_monitor.py`)
- `config.py` — load config, write back `[ui] mode` line-by-line preserving comments
- `usage_client.py` — `UsageClient.fetch()` + `UsageData` parsing
- `poller.py` — background polling thread, calls back into ModeManager
- `mode_manager.py` — owns Poller + current View, handles mode switches, caches last data
- `views/__init__.py` — empty package marker
- `views/base.py` — `View` abstract base (`start`, `stop`, `on_update`)
- `views/overlay.py` — current floating window (moved + extended with mode-switch menu)
- `views/tray.py` — pystray icon, popup panel, dynamic icon image generation
- `views/cli.py` — single-line ANSI terminal output + `q` to quit
- `views/autohide.py` — subclass of overlay with edge-slide behavior
- `tests/test_config.py`
- `tests/test_usage_client.py`
- `tests/test_poller.py`
- `tests/test_mode_manager.py`
- `tests/__init__.py` — empty package marker

**Modified files:**
- `claude_monitor.py` — becomes a thin entry point (argparse + ModeManager bootstrap). Existing 333-line body is migrated into the new modules.
- `config.ini.example` — adds `[ui] mode`, `[tray]`, `[autohide]` sections
- `README.md` — documents new modes, dependencies, CLI flags

**Untouched files:**
- `claude_monitor.bat`, `.gitignore`, `LICENSE`, `screenshot.png`

---

## Task 1: Install dependencies and update config.ini.example

**Files:**
- Modify: `config.ini.example`

- [ ] **Step 1: Install new dependencies**

Run:
```
pip install pystray Pillow pytest
```

Expected: successful install. `pystray` brings `Pillow` transitively but specify both for clarity. `pytest` is for the test suite.

- [ ] **Step 2: Update `config.ini.example`**

Replace the entire file contents with:

```ini
[claude]
cookies       = sessionKey=sk-ant-...; cf_clearance=...; ...
org_id        = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
poll_interval = 60

[ui]
language = en              ; en | ko
mode     = overlay         ; overlay | tray | cli | autohide

[tray]
popup_position = above     ; above | below

[autohide]
edge          = right      ; right | left | top | bottom
peek_pixels   = 3
slide_ms      = 150
hide_delay_ms = 1500
```

- [ ] **Step 3: Verify file**

Run: `python -c "import configparser; c = configparser.ConfigParser(); c.read('config.ini.example'); print(list(c.sections()))"`

Expected output: `['claude', 'ui', 'tray', 'autohide']`

- [ ] **Step 4: Commit**

```
git add config.ini.example
git commit -m "chore: add multi-mode config keys to config.ini.example"
```

---

## Task 2: Extract i18n module

**Files:**
- Create: `i18n.py`
- Modify: `claude_monitor.py` (remove TRANSLATIONS, import from i18n)

- [ ] **Step 1: Create `i18n.py` with current strings + new mode-switch strings**

```python
"""Translation strings for UI labels."""

TRANSLATIONS = {
    "en": {
        "session_5h":            "5h session",
        "label_7d":              "7d",
        "reset":                 "Reset",
        "reset_7d":              "7d Reset",
        "menu_refresh":          "Refresh now",
        "menu_quit":             "Quit",
        "menu_switch_mode":      "Switch mode",
        "mode_overlay":          "Overlay",
        "mode_tray":             "Tray",
        "mode_cli":              "CLI",
        "mode_autohide":         "Autohide",
        "menu_force_show":       "Force show (lock open)",
        "cli_quit_hint":         "Press 'q' + Enter to quit",
        "cli_mode_needs_console": "CLI mode requires python.exe (a visible console). Aborting switch.",
        "resetting_soon":        "Resetting soon",
    },
    "ko": {
        "session_5h":            "5h 세션",
        "label_7d":              "7일",
        "reset":                 "리셋",
        "reset_7d":              "7일 리셋",
        "menu_refresh":          "지금 새로고침",
        "menu_quit":             "종료",
        "menu_switch_mode":      "모드 전환",
        "mode_overlay":          "오버레이",
        "mode_tray":             "트레이",
        "mode_cli":              "CLI",
        "mode_autohide":         "자동 숨김",
        "menu_force_show":       "강제 표시 (잠금)",
        "cli_quit_hint":         "종료하려면 'q' + Enter",
        "cli_mode_needs_console": "CLI 모드는 콘솔이 있는 python.exe 가 필요합니다. 전환 취소.",
        "resetting_soon":        "곧 리셋",
    },
}

_current_lang = "en"


def set_language(lang):
    global _current_lang
    _current_lang = lang if lang in TRANSLATIONS else "en"


def T(key):
    return TRANSLATIONS[_current_lang].get(key, key)
```

- [ ] **Step 2: Quick smoke test**

Run:
```
python -c "from i18n import set_language, T; set_language('ko'); print(T('menu_quit'))"
```

Expected output: `종료`

- [ ] **Step 3: Commit (claude_monitor.py update happens in Task 12)**

```
git add i18n.py
git commit -m "feat: extract i18n module with mode-switch strings"
```

---

## Task 3: Config loader/saver

**Files:**
- Create: `config.py`
- Create: `tests/__init__.py` (empty)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test in `tests/test_config.py`**

```python
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


def test_save_mode_handles_empty_value_line(tmp_path):
    """An empty `mode =` line must be filled, not duplicated."""
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nlanguage = en\nmode =\n", encoding="utf-8")
    save_mode(p, "tray")
    text = p.read_text(encoding="utf-8")
    assert text.count("mode =") == 1 or text.count("mode=") == 1
    assert "tray" in text
    cfg = Config.load(p)
    assert cfg.mode == "tray"


def test_save_mode_roundtrip(cfg_file):
    """save_mode then Config.load yields the saved mode and other keys survive."""
    save_mode(cfg_file, "autohide")
    cfg = Config.load(cfg_file)
    assert cfg.mode == "autohide"
    assert cfg.language == "ko"
    assert cfg.autohide_edge == "right"
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_config.py -v`
Expected: ModuleNotFoundError: No module named 'config' (or all tests fail).

- [ ] **Step 3: Implement `config.py`**

```python
"""Config file loading + targeted line-based saving of the `mode` key."""

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

VALID_MODES = ("overlay", "tray", "cli", "autohide")


@dataclass
class Config:
    cookies: str
    org_id: str
    poll_interval: int
    language: str
    mode: str
    tray_popup_position: str
    autohide_edge: str
    autohide_peek_pixels: int
    autohide_slide_ms: int
    autohide_hide_delay_ms: int

    @classmethod
    def load(cls, path):
        cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
        cp.read(path, encoding="utf-8")

        mode = cp.get("ui", "mode", fallback="overlay").strip().lower()
        if mode not in VALID_MODES:
            mode = "overlay"

        return cls(
            cookies=cp.get("claude", "cookies", fallback=""),
            org_id=cp.get("claude", "org_id", fallback=""),
            poll_interval=cp.getint("claude", "poll_interval", fallback=60),
            language=cp.get("ui", "language", fallback="en").strip().lower(),
            mode=mode,
            tray_popup_position=cp.get("tray", "popup_position", fallback="above"),
            autohide_edge=cp.get("autohide", "edge", fallback="right"),
            autohide_peek_pixels=cp.getint("autohide", "peek_pixels", fallback=3),
            autohide_slide_ms=cp.getint("autohide", "slide_ms", fallback=150),
            autohide_hide_delay_ms=cp.getint("autohide", "hide_delay_ms", fallback=1500),
        )


def save_mode(path: Path, mode: str):
    """Rewrite [ui] mode = <mode> in-place, preserving comments and ordering.

    configparser's write() would clobber inline comments, so we patch the file
    line-by-line. If [ui] or `mode` does not exist, append them.
    """
    path = Path(path)
    if not path.exists():
        path.write_text(f"[ui]\nmode = {mode}\n", encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_ui = False
    ui_seen = False
    mode_written = False
    out = []

    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    # [^\S\n]* = horizontal whitespace only, so the prefix capture can't swallow
    # the line's trailing newline. (\S*) matches an empty value too, so an
    # `mode =` line is patched in place instead of duplicated.
    mode_re    = re.compile(r"^(\s*mode\s*=[^\S\n]*)(\S*)(.*)$")

    for line in lines:
        sec = section_re.match(line)
        if sec:
            # Leaving [ui] without writing mode -> append before this section
            if in_ui and not mode_written:
                out.append(f"mode = {mode}\n")
                mode_written = True
            in_ui = sec.group(1).strip().lower() == "ui"
            if in_ui:
                ui_seen = True
            out.append(line)
            continue

        if in_ui and not mode_written:
            m = mode_re.match(line)
            if m:
                prefix, _old, tail = m.groups()
                out.append(f"{prefix}{mode}{tail}\n" if not tail.endswith("\n") else f"{prefix}{mode}{tail}")
                mode_written = True
                continue
        out.append(line)

    if in_ui and not mode_written:
        # File ended inside [ui] without a mode key
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"mode = {mode}\n")
        mode_written = True
    elif not ui_seen:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append("\n[ui]\n")
        out.append(f"mode = {mode}\n")

    path.write_text("".join(out), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add config.py tests/test_config.py tests/__init__.py
git commit -m "feat: add Config loader and line-based save_mode"
```

---

## Task 4: UsageClient + UsageData

**Files:**
- Create: `usage_client.py`
- Test: `tests/test_usage_client.py`

- [ ] **Step 1: Write failing test in `tests/test_usage_client.py`**

```python
from usage_client import UsageData, parse_usage


def test_parse_wrapped_under_usage_key():
    raw = {"usage": {"five_hour": {"utilization": 42.5, "resets_at": "2026-05-14T18:00:00+00:00"}}}
    data = parse_usage(raw)
    assert data.five_hour_pct == 42.5
    assert data.five_hour_resets_at == "2026-05-14T18:00:00+00:00"


def test_parse_flat_shape():
    raw = {"five_hour": {"utilization": 10}, "seven_day": {"utilization": 5}}
    data = parse_usage(raw)
    assert data.five_hour_pct == 10
    assert data.seven_day_pct == 5


def test_parse_handles_missing_fields():
    data = parse_usage({})
    assert data.five_hour_pct is None
    assert data.seven_day_pct is None
    assert data.seven_day_sonnet_pct is None
    assert data.extra_used == 0
    assert data.extra_limit == 0
    assert data.extra_pct == 0


def test_parse_extra_credits():
    raw = {"extra_usage": {"used_credits": 12, "monthly_limit": 100, "utilization": 12.0}}
    data = parse_usage(raw)
    assert data.extra_used == 12
    assert data.extra_limit == 100
    assert data.extra_pct == 12.0
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_usage_client.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `usage_client.py`**

```python
"""HTTP fetch + parsing of Claude.ai /usage endpoint."""

from dataclasses import dataclass
from typing import Optional

try:
    from curl_cffi import requests
    IMPERSONATE = "chrome124"
except ImportError:
    import requests
    IMPERSONATE = None


@dataclass
class UsageData:
    five_hour_pct: Optional[float] = None
    five_hour_resets_at: Optional[str] = None
    seven_day_pct: Optional[float] = None
    seven_day_resets_at: Optional[str] = None
    seven_day_sonnet_pct: Optional[float] = None
    extra_used: float = 0
    extra_limit: float = 0
    extra_pct: float = 0.0


def parse_usage(raw):
    """Normalize the /usage payload, which comes either as {usage: {...}} or flat."""
    body = raw.get("usage", raw) if isinstance(raw, dict) else {}
    fh = body.get("five_hour") or {}
    sd = body.get("seven_day") or {}
    sn = body.get("seven_day_sonnet") or {}
    ex = body.get("extra_usage") or {}
    return UsageData(
        five_hour_pct=fh.get("utilization"),
        five_hour_resets_at=fh.get("resets_at"),
        seven_day_pct=sd.get("utilization"),
        seven_day_resets_at=sd.get("resets_at"),
        seven_day_sonnet_pct=sn.get("utilization"),
        extra_used=ex.get("used_credits", 0),
        extra_limit=ex.get("monthly_limit", 0),
        extra_pct=ex.get("utilization", 0),
    )


class UsageClient:
    def __init__(self, org_id: str, cookies: str):
        self.url = f"https://claude.ai/api/organizations/{org_id}/usage"
        self.cookies = cookies

    def fetch(self) -> Optional[UsageData]:
        try:
            kwargs = dict(
                headers={
                    "Cookie": self.cookies,
                    "Accept": "application/json",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                    "Referer": "https://claude.ai/settings/usage",
                    "Origin": "https://claude.ai",
                },
                timeout=10,
            )
            if IMPERSONATE:
                kwargs["impersonate"] = IMPERSONATE
            r = requests.get(self.url, **kwargs)
            r.raise_for_status()
            return parse_usage(r.json())
        except Exception as e:
            print(f"[fetch error] {e}")
            return None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_usage_client.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```
git add usage_client.py tests/test_usage_client.py
git commit -m "feat: add UsageClient and UsageData parser"
```

---

## Task 5: Background Poller

**Files:**
- Create: `poller.py`
- Test: `tests/test_poller.py`

- [ ] **Step 1: Write failing test in `tests/test_poller.py`**

```python
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
    time.sleep(0.05)
    assert received == ["d1"]            # initial fetch happens eagerly on start
    p.trigger()
    time.sleep(0.05)
    p.stop()
    assert received == ["d1", "d2"]      # trigger forces the next fetch without waiting the interval
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_poller.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `poller.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_poller.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add poller.py tests/test_poller.py
git commit -m "feat: add background Poller with trigger support"
```

---

## Task 6: View base class

**Files:**
- Create: `views/__init__.py` (empty)
- Create: `views/base.py`

- [ ] **Step 1: Create empty package marker**

Run:
```
mkdir views
type nul > views\__init__.py
```

(On bash: `mkdir -p views && touch views/__init__.py`)

- [ ] **Step 2: Implement `views/base.py`**

```python
"""Abstract base for display views."""

from abc import ABC, abstractmethod
from typing import Optional

from usage_client import UsageData


class View(ABC):
    """A display surface. Owns its UI lifecycle; receives usage updates via on_update."""

    def __init__(self, manager):
        # ModeManager reference; views call back via manager.request_switch / .request_refresh / .request_quit
        self.manager = manager

    @abstractmethod
    def start(self, initial: Optional[UsageData]) -> None:
        """Build UI. If `initial` is provided, render it immediately."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down UI. Idempotent."""

    @abstractmethod
    def on_update(self, data: UsageData) -> None:
        """Fresh data arrived. Tk views get this on the main thread; cli/tray on the Poller thread."""
```

- [ ] **Step 3: Commit**

```
git add views/__init__.py views/base.py
git commit -m "feat: add View abstract base"
```

---

## Task 7: Overlay view (move existing UI into a View)

**Files:**
- Create: `views/overlay.py`

- [ ] **Step 1: Implement `views/overlay.py`**

Most of this code is lifted from the existing `claude_monitor.py` `ClaudeOverlay` class. Key changes:
- Wrapped as a `View` subclass.
- `on_update` replaces the old `_refresh_ui` (now takes a `UsageData` instead of reading `self.data` dict).
- Right-click menu gains "Switch mode" submenu and calls back into `manager.request_switch(...)`.
- Refresh button calls `manager.request_refresh()`; Quit calls `manager.request_quit()`.

```python
"""Overlay mode: the original floating, always-on-top window."""

import tkinter as tk
from datetime import datetime, timezone
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.base import View

BG  = "#1C1C1E"
DIM = "#AEAEB2"
SEP = "#2C2C2E"


def pct_color(pct):
    if pct is None:
        return "#636366"
    if pct < 60:
        return "#30D158"
    if pct < 85:
        return "#FFD60A"
    return "#FF453A"


def time_until(iso_str):
    if not iso_str:
        return "?"
    try:
        reset = datetime.fromisoformat(iso_str)
        now   = datetime.now(timezone.utc)
        secs  = int((reset - now).total_seconds())
        if secs <= 0:
            return T("resetting_soon")
        d, r1 = divmod(secs, 86400)
        h, r2 = divmod(r1, 3600)
        m      = r2 // 60
        if d:
            return f"{d}d {h}h"
        return f"{h}h {m:02d}m" if h else f"{m}m"
    except Exception:
        return "?"


class OverlayView(View):
    W, H = 230, 178

    def __init__(self, manager):
        super().__init__(manager)
        self.root = None
        self._tick_after_id = None
        self._last = None

    def start(self, initial: Optional[UsageData]) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.H - 56}")

        self._build_ui()
        self._bind_drag()
        self._bind_menu()

        if initial:
            self.on_update(initial)

        self._tick()
        # Note: caller (ModeManager) drives mainloop via run_mainloop()

    def run_mainloop(self):
        if self.root:
            self.root.mainloop()

    def stop(self) -> None:
        if self._tick_after_id and self.root:
            try:
                self.root.after_cancel(self._tick_after_id)
            except Exception:
                pass
            self._tick_after_id = None
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(hdr, text="Claude", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left")
        self.lbl_updated = tk.Label(hdr, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lbl_updated.pack(side="right")

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        row5 = tk.Frame(self.root, bg=BG)
        row5.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(row5, text=T("session_5h"), bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left", anchor="s", pady=(0, 4))
        self.lbl_5h_reset = tk.Label(row5, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lbl_5h_reset.pack(side="right", anchor="s", pady=(0, 4))

        self.lbl_5h = tk.Label(self.root, text="—", bg=BG, fg="#30D158", font=("Segoe UI", 32, "bold"))
        self.lbl_5h.pack(anchor="w", padx=10)

        outer = tk.Frame(self.root, bg="#3A3A3C", height=5)
        outer.pack(fill="x", padx=10, pady=(0, 6))
        outer.pack_propagate(False)
        self.bar = tk.Frame(outer, bg="#30D158", height=5)
        self.bar.place(x=0, y=0, relheight=1, relwidth=0)

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        row7 = tk.Frame(self.root, bg=BG)
        row7.pack(fill="x", padx=10, pady=(5, 2))
        self.lbl_7d     = tk.Label(row7, text=f"{T('label_7d')}  —%", bg=BG, fg="#EBEBF5", font=("Segoe UI", 10))
        self.lbl_7d.pack(side="left")
        self.lbl_sonnet = tk.Label(row7, text="Sonnet  —%", bg=BG, fg="#EBEBF5", font=("Segoe UI", 10))
        self.lbl_sonnet.pack(side="right")

        self.lbl_7d_reset = tk.Label(self.root, text="", bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w")
        self.lbl_7d_reset.pack(fill="x", padx=10, pady=(0, 2))

        self.lbl_extra = tk.Label(self.root, text="Extra: —", bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w")
        self.lbl_extra.pack(fill="x", padx=10, pady=(0, 6))

    def on_update(self, data: UsageData) -> None:
        self._last = data
        c5 = pct_color(data.five_hour_pct)
        self.lbl_5h.config(text=f"{data.five_hour_pct:.0f}%" if data.five_hour_pct is not None else "—", fg=c5)
        self.bar.config(bg=c5)
        self.bar.place(relwidth=(data.five_hour_pct or 0) / 100)
        self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(data.five_hour_resets_at)}")

        self.lbl_7d.config(
            text=f"{T('label_7d')}  {data.seven_day_pct:.0f}%" if data.seven_day_pct is not None else f"{T('label_7d')}  —%",
            fg=pct_color(data.seven_day_pct),
        )
        self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(data.seven_day_resets_at)}")

        self.lbl_sonnet.config(
            text=f"Sonnet  {data.seven_day_sonnet_pct:.0f}%" if data.seven_day_sonnet_pct is not None else "Sonnet  —",
            fg=pct_color(data.seven_day_sonnet_pct),
        )

        self.lbl_extra.config(text=f"Extra: {data.extra_used:.0f}/{data.extra_limit} ({data.extra_pct:.1f}%)")

        now = datetime.now().strftime("%H:%M")
        self.lbl_updated.config(text=now)

    def _tick(self):
        if not self.root:
            return
        self.root.attributes("-topmost", False)
        self.root.attributes("-topmost", True)
        self.root.lift()
        if self._last:
            self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(self._last.five_hour_resets_at)}")
            self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(self._last.seven_day_resets_at)}")
        self._tick_after_id = self.root.after(10_000, self._tick)

    def _bind_drag(self):
        self.root.bind("<Button-1>",  self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, e):
        self._dx = e.x
        self._dy = e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _bind_menu(self):
        self.root.bind("<Button-3>", self._show_menu)

    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        switch = tk.Menu(menu, tearoff=0, bg="#2C2C2E", fg="white",
                         activebackground="#3A3A3C", activeforeground="white")
        switch.add_command(label=T("mode_overlay"),  command=lambda: self.manager.request_switch("overlay"))
        switch.add_command(label=T("mode_tray"),     command=lambda: self.manager.request_switch("tray"))
        switch.add_command(label=T("mode_cli"),      command=lambda: self.manager.request_switch("cli"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)
```

- [ ] **Step 2: Manual smoke test (defer to Task 12 when entry point is ready)**

The overlay view depends on a working ModeManager (Task 8) and entry point (Task 12). End-to-end run happens then.

- [ ] **Step 3: Commit**

```
git add views/overlay.py
git commit -m "feat: port overlay to View class with mode-switch menu"
```

---

## Task 8: ModeManager

**Files:**
- Create: `mode_manager.py`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing test in `tests/test_mode_manager.py`**

The manager has UI-coupled behavior; we test only the non-UI parts (caching, mode persistence dispatch). Fake view records calls.

```python
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
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_mode_manager.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `mode_manager.py`**

```python
"""ModeManager: owns Poller + current View, serializes mode switches."""

import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from config import save_mode as cfg_save_mode


class ModeManager:
    def __init__(
        self,
        cfg_path: Path,
        view_factories: Dict[str, Callable],
        poller,
        save_mode: bool,
    ):
        self.cfg_path = Path(cfg_path)
        self.view_factories = view_factories
        self.poller = poller
        self.save_mode = save_mode

        self.current_mode: Optional[str] = None
        self.current_view = None
        self.last_data = None
        self._quit_requested = False
        self._pending_switch: Optional[str] = None

    # -- Lifecycle ---------------------------------------------------------

    def start_initial(self, mode: str):
        if mode not in self.view_factories:
            mode = "overlay"
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)

    def run(self):
        """Drive whichever main loop the current view needs.

        Tk-based views: call view.run_mainloop() and re-enter when a switch is requested.
        CLI view: call view.run_mainloop() which blocks on stdin.
        Tray view: pystray's icon.run() blocks.
        """
        while not self._quit_requested:
            run = getattr(self.current_view, "run_mainloop", None)
            if callable(run):
                run()
            # If a switch was queued (the view exited its loop because of stop()), perform it
            if self._pending_switch:
                target = self._pending_switch
                self._pending_switch = None
                self._do_switch(target)
            else:
                # No pending switch; loop exited for quit
                break
        # Cleanup on quit
        if self.current_view:
            self.current_view.stop()
        if self.poller:
            self.poller.stop()

    # -- Poll callback (called from poller thread) -------------------------

    def on_poll_data(self, data):
        self.last_data = data
        view = self.current_view
        if view is None:
            return
        root = getattr(view, "root", None)
        if root is not None:
            # Tk view: marshal onto the main thread. Guard the callback so a view
            # swapped out between scheduling and running is skipped, and never fall
            # through to a direct cross-thread call if scheduling fails.
            try:
                root.after(0, lambda v=view: v.on_update(data) if v is self.current_view else None)
            except Exception:
                # root was destroyed mid-switch; the next poll reaches the new view.
                pass
            return
        # Non-Tk view (cli/tray), or a Tk view already stopped (root is None).
        # Skip if it is no longer the current view so a stale view isn't touched.
        if view is self.current_view:
            view.on_update(data)

    # -- Public requests from views ----------------------------------------

    def request_switch(self, mode: str):
        if mode == self.current_mode or mode not in self.view_factories:
            return
        # CLI → GUI check: CLI mode has no menu, but autohide/overlay/tray → cli needs a console.
        if mode == "cli" and not self._console_attached():
            self._show_no_console_error()
            return
        # Stop view; loop exit triggers _do_switch
        self._pending_switch = mode
        if self.current_view:
            self.current_view.stop()

    def request_refresh(self):
        if self.poller:
            self.poller.trigger()

    def request_quit(self):
        self._quit_requested = True
        if self.current_view:
            self.current_view.stop()

    # -- Internal switch -----------------------------------------------------

    def _do_switch(self, mode: str):
        if self.save_mode:
            try:
                cfg_save_mode(self.cfg_path, mode)
            except Exception as e:
                print(f"[mode save error] {e}")
        # Stop the outgoing view before constructing the next one.
        # View.stop() is idempotent, so a prior stop() from request_switch() is harmless.
        if self.current_view:
            self.current_view.stop()
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)

    @staticmethod
    def _console_attached() -> bool:
        try:
            return sys.stdout is not None and sys.stdout.isatty() and os.isatty(1)
        except Exception:
            return False

    def _show_no_console_error(self):
        # Best effort: show a tk messagebox if a Tk view is up
        try:
            import tkinter.messagebox as mb
            from i18n import T
            mb.showerror("CLI mode", T("cli_mode_needs_console"))
        except Exception:
            print("[mode] cli mode needs console")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_mode_manager.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```
git add mode_manager.py tests/test_mode_manager.py
git commit -m "feat: add ModeManager with view lifecycle and cache replay"
```

---

## Task 9: Tray view (pystray + popup)

**Files:**
- Create: `views/tray.py`

- [ ] **Step 1: Implement `views/tray.py`**

```python
"""Tray mode: pystray icon with color+number, hover tooltip, left-click popup."""

import queue
import threading
import tkinter as tk
from datetime import datetime
from typing import Optional

import pystray
from PIL import Image, ImageDraw, ImageFont

from i18n import T
from usage_client import UsageData
from views.base import View
from views.overlay import pct_color, time_until

ICON_SIZE = 64  # Rendered at 64 for clarity; Windows downsizes to 16/24/32


def _font(size: int):
    try:
        return ImageFont.truetype("seguibl.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("arialbd.ttf", size)
        except Exception:
            return ImageFont.load_default()


def make_icon_image(pct: Optional[float]) -> Image.Image:
    """Solid color background with the percentage drawn on top."""
    color = pct_color(pct)
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), color)
    draw = ImageDraw.Draw(img)
    if pct is None:
        text = "—"
    elif pct >= 100:
        text = "!!"
    else:
        text = f"{int(pct)}"
    font_size = 40 if len(text) == 1 else 32
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((ICON_SIZE - tw) / 2 - bbox[0], (ICON_SIZE - th) / 2 - bbox[1]),
              text, fill="white", font=font)
    return img


def make_tooltip(data: Optional[UsageData]) -> str:
    if not data:
        return "Claude Usage  (loading)"
    now = datetime.now().strftime("%H:%M")
    return (
        f"Claude Usage  {now}\n"
        f"5h session {fmt(data.five_hour_pct)}  · Reset {time_until(data.five_hour_resets_at)}\n"
        f"7d         {fmt(data.seven_day_pct)}  · Reset {time_until(data.seven_day_resets_at)}\n"
        f"Sonnet     {fmt(data.seven_day_sonnet_pct)}\n"
        f"Extra      {(data.extra_used or 0):.0f}/{data.extra_limit or 0} ({(data.extra_pct or 0):.1f}%)"
    )


def fmt(pct):
    return f"{int(pct):>3}%" if pct is not None else "  —%"


class TrayView(View):
    def __init__(self, manager):
        super().__init__(manager)
        self.icon: Optional[pystray.Icon] = None
        self._popup: Optional[tk.Toplevel] = None
        self._last: Optional[UsageData] = None
        self._tk_root: Optional[tk.Tk] = None
        self._stop = threading.Event()
        # Cross-thread work queue: pystray/Poller threads enqueue, run_mainloop drains.
        self._tk_queue: "queue.Queue" = queue.Queue()

    # ModeManager calls start() on the main thread.
    def start(self, initial: Optional[UsageData]) -> None:
        self._last = initial
        # Hidden Tk root so we can spawn popup Toplevels later.
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()
        self.icon = pystray.Icon(
            "claude_monitor",
            icon=make_icon_image(initial.five_hour_pct if initial else None),
            title=make_tooltip(initial),
            menu=self._build_menu(),
        )
        # pystray's run() blocks; run it on a daemon thread. Tk is pumped by run_mainloop().
        threading.Thread(target=self.icon.run, daemon=True).start()

    def run_mainloop(self):
        # Main thread: pump Tk and drain the cross-thread work queue.
        while not self._stop.is_set():
            root = self._tk_root
            if root is None:
                break
            try:
                self._drain_queue()
                root.update()
            except tk.TclError:
                break
            self._stop.wait(0.05)
        # Tear down Tk resources on the main thread, after the loop exits.
        self._teardown_tk()

    def _drain_queue(self):
        while True:
            try:
                fn = self._tk_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                print(f"[tray queue error] {e}")

    def _post(self, fn):
        """Schedule a callable to run on the Tk main thread via run_mainloop's pump."""
        self._tk_queue.put(fn)

    def stop(self) -> None:
        # Idempotent. Only signals stop and tears down the pystray icon here;
        # Tk teardown is deferred to run_mainloop (main thread) to avoid
        # touching Tk from the pystray thread.
        self._stop.set()
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def _teardown_tk(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
        if self._tk_root is not None:
            try:
                self._tk_root.destroy()
            except Exception:
                pass
            self._tk_root = None

    def on_update(self, data: UsageData) -> None:
        # May be called from the Poller thread. pystray icon updates are safe
        # from any thread; Tk popup refresh is deferred to the main thread.
        self._last = data
        if self.icon:
            try:
                self.icon.icon = make_icon_image(data.five_hour_pct)
                self.icon.title = make_tooltip(data)
            except Exception as e:
                print(f"[tray update error] {e}")
        if self._popup is not None:
            self._post(self._refresh_popup)

    # -- Menu / interactions ------------------------------------------------

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(T("menu_switch_mode"), pystray.Menu(
                pystray.MenuItem(T("mode_overlay"),  lambda: self.manager.request_switch("overlay")),
                pystray.MenuItem(T("mode_tray"),     lambda: None, enabled=False),
                pystray.MenuItem(T("mode_cli"),      lambda: self.manager.request_switch("cli")),
                pystray.MenuItem(T("mode_autohide"), lambda: self.manager.request_switch("autohide")),
            )),
            pystray.MenuItem(T("menu_refresh"), lambda: self.manager.request_refresh()),
            pystray.MenuItem(T("menu_quit"),    lambda: self.manager.request_quit()),
            pystray.MenuItem("show", self._on_left_click, default=True, visible=False),
        )

    def _on_left_click(self, icon, item):
        # pystray callback (pystray thread) — defer to the Tk main thread.
        self._post(self._toggle_popup)

    def _toggle_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self):
        if self._tk_root is None:
            return
        p = tk.Toplevel(self._tk_root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg="#1C1C1E")
        p.geometry("240x170")
        # Place near bottom-right corner (above tray)
        sw = p.winfo_screenwidth()
        sh = p.winfo_screenheight()
        p.geometry(f"+{sw - 260}+{sh - 230}")

        body = tk.Label(p, text=make_tooltip(self._last), bg="#1C1C1E", fg="#EBEBF5",
                        font=("Segoe UI", 10), justify="left", anchor="nw")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        def close(_=None):
            try:
                p.destroy()
            except Exception:
                pass
            if self._popup is p:
                self._popup = None

        p.bind("<FocusOut>", close)
        p.bind("<Button-1>", close)
        p.focus_force()
        self._popup = p

    def _refresh_popup(self):
        if self._popup is None:
            return
        try:
            for child in self._popup.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(text=make_tooltip(self._last))
                    break
        except Exception:
            pass
```

- [ ] **Step 2: Commit**

```
git add views/tray.py
git commit -m "feat: add Tray view with color+number icon and popup panel"
```

---

## Task 10: CLI view

**Files:**
- Create: `views/cli.py`

- [ ] **Step 1: Implement `views/cli.py`**

```python
"""CLI mode: single-line ANSI output redrawn in place; 'q' + Enter to quit."""

import sys
import threading
from datetime import datetime
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.base import View
from views.overlay import time_until

RESET   = "\x1b[0m"
GREEN   = "\x1b[32m"
YELLOW  = "\x1b[33m"
RED     = "\x1b[31m"
DIM     = "\x1b[90m"


def color_for(pct):
    if pct is None:
        return DIM
    if pct < 60:
        return GREEN
    if pct < 85:
        return YELLOW
    return RED


def render_line(data: Optional[UsageData]) -> str:
    if not data:
        return "loading..."
    parts = [
        f"5h {color_for(data.five_hour_pct)}{_pct(data.five_hour_pct)}{RESET}",
        f"7d {color_for(data.seven_day_pct)}{_pct(data.seven_day_pct)}{RESET}",
        f"Sonnet {color_for(data.seven_day_sonnet_pct)}{_pct(data.seven_day_sonnet_pct)}{RESET}",
        f"Extra {(data.extra_used or 0):.0f}/{data.extra_limit or 0}",
        f"{T('reset')} {time_until(data.five_hour_resets_at)}",
        f"[{datetime.now().strftime('%H:%M')}]",
    ]
    return " │ ".join(parts)


def _pct(pct):
    return f"{int(pct):>3}%" if pct is not None else "  —%"


class CLIView(View):
    def __init__(self, manager):
        super().__init__(manager)
        self._stop = threading.Event()
        self._last: Optional[UsageData] = None
        self._lock = threading.Lock()
        self._input_thread: Optional[threading.Thread] = None

    def start(self, initial: Optional[UsageData]) -> None:
        # Enable ANSI on Windows 10+ conhost
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass
        self._last = initial
        print(f"{DIM}{T('cli_quit_hint')}{RESET}")
        self._redraw()

    def run_mainloop(self):
        # Block on stdin for 'q' + Enter
        self._input_thread = threading.Thread(target=self._stdin_loop, daemon=True)
        self._input_thread.start()
        self._stop.wait()
        # Clean line and add newline before exit
        sys.stdout.write("\r\x1b[K\n")
        sys.stdout.flush()

    def stop(self) -> None:
        self._stop.set()

    def on_update(self, data: UsageData) -> None:
        self._last = data
        self._redraw()

    def _redraw(self):
        with self._lock:
            sys.stdout.write("\r\x1b[K" + render_line(self._last))
            sys.stdout.flush()

    def _stdin_loop(self):
        try:
            while not self._stop.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip().lower() == "q":
                    self.manager.request_quit()
                    return
        except Exception:
            pass
```

- [ ] **Step 2: Commit**

```
git add views/cli.py
git commit -m "feat: add CLI view with single-line ANSI output"
```

---

## Task 11: Autohide view

**Files:**
- Create: `views/autohide.py`

- [ ] **Step 1: Implement `views/autohide.py`**

```python
"""Autohide mode: docks the overlay to a screen edge; slides in on hover."""

import tkinter as tk
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.overlay import OverlayView


class AutohideView(OverlayView):
    """Overlay that hides to a screen edge, peeking PEEK px until mouse hover."""

    EDGE = "right"
    PEEK = 3
    SLIDE_MS = 150
    HIDE_DELAY_MS = 1500
    SLIDE_STEPS = 10

    def __init__(self, manager):
        super().__init__(manager)
        # Read config off the manager so behavior is data-driven
        cfg = getattr(manager, "config", None)
        if cfg is not None:
            self.EDGE = cfg.autohide_edge
            self.PEEK = cfg.autohide_peek_pixels
            self.SLIDE_MS = cfg.autohide_slide_ms
            self.HIDE_DELAY_MS = cfg.autohide_hide_delay_ms
        self._shown = False
        self._hover = False
        self._force_show = False
        self._hide_after_id = None
        self._poll_after_id = None

    def start(self, initial: Optional[UsageData]) -> None:
        super().start(initial)
        # Reposition to docked state
        self.root.after(50, self._dock_initial)
        self._poll_hover()

    def stop(self) -> None:
        if self._hide_after_id and self.root:
            try:
                self.root.after_cancel(self._hide_after_id)
            except Exception:
                pass
            self._hide_after_id = None
        if self._poll_after_id and self.root:
            try:
                self.root.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        super().stop()

    # Override the right-click menu to add "Force show"
    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        switch = tk.Menu(menu, tearoff=0, bg="#2C2C2E", fg="white",
                         activebackground="#3A3A3C", activeforeground="white")
        switch.add_command(label=T("mode_overlay"),  command=lambda: self.manager.request_switch("overlay"))
        switch.add_command(label=T("mode_tray"),     command=lambda: self.manager.request_switch("tray"))
        switch.add_command(label=T("mode_cli"),      command=lambda: self.manager.request_switch("cli"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        menu.add_checkbutton(label=T("menu_force_show"),
                             command=self._toggle_force_show,
                             variable=tk.BooleanVar(value=self._force_show))
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)

    def _toggle_force_show(self):
        self._force_show = not self._force_show
        if self._force_show:
            self._slide_in(force=True)

    def _dock_initial(self):
        self._geom_hidden = self._compute_hidden_geom()
        self._geom_shown  = self._compute_shown_geom()
        self.root.geometry(self._geom_hidden)
        self._shown = False

    def _compute_hidden_geom(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if self.EDGE == "right":
            return f"{self.W}x{self.H}+{sw - self.PEEK}+{sh - self.H - 56}"
        if self.EDGE == "left":
            return f"{self.W}x{self.H}+{self.PEEK - self.W}+{sh - self.H - 56}"
        if self.EDGE == "top":
            return f"{self.W}x{self.H}+{sw - self.W - 16}+{self.PEEK - self.H}"
        # bottom
        return f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.PEEK}"

    def _compute_shown_geom(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if self.EDGE == "right":
            return f"{self.W}x{self.H}+{sw - self.W - 4}+{sh - self.H - 56}"
        if self.EDGE == "left":
            return f"{self.W}x{self.H}+4+{sh - self.H - 56}"
        if self.EDGE == "top":
            return f"{self.W}x{self.H}+{sw - self.W - 16}+4"
        # bottom
        return f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.H - 56}"

    def _poll_hover(self):
        if not self.root:
            return
        try:
            x, y = self.root.winfo_pointerxy()
        except Exception:
            self._poll_after_id = self.root.after(200, self._poll_hover)
            return
        in_zone = self._cursor_in_active_zone(x, y)
        if in_zone and not self._hover:
            self._hover = True
            if not self._shown:
                self._slide_in()
        elif not in_zone and self._hover:
            self._hover = False
            if self._shown and not self._force_show:
                self._schedule_hide()
        self._poll_after_id = self.root.after(150, self._poll_hover)

    def _cursor_in_active_zone(self, x, y):
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.W
        rh = self.H
        if self._shown:
            return rx <= x <= rx + rw and ry <= y <= ry + rh
        # Hidden state — sensitive area is the peek strip
        if self.EDGE == "right":
            sw = self.root.winfo_screenwidth()
            return sw - self.PEEK <= x <= sw and ry <= y <= ry + rh
        if self.EDGE == "left":
            return 0 <= x <= self.PEEK and ry <= y <= ry + rh
        if self.EDGE == "top":
            return rx <= x <= rx + rw and 0 <= y <= self.PEEK
        sh = self.root.winfo_screenheight()
        return rx <= x <= rx + rw and sh - self.PEEK <= y <= sh

    def _slide_in(self, force=False):
        if self._shown and not force:
            return
        self._cancel_hide()
        self._animate(self._geom_hidden, self._geom_shown)
        self._shown = True

    def _slide_out(self):
        if not self._shown or self._force_show:
            return
        self._animate(self._geom_shown, self._geom_hidden)
        self._shown = False

    def _schedule_hide(self):
        self._cancel_hide()
        self._hide_after_id = self.root.after(self.HIDE_DELAY_MS, self._slide_out)

    def _cancel_hide(self):
        if self._hide_after_id:
            try:
                self.root.after_cancel(self._hide_after_id)
            except Exception:
                pass
            self._hide_after_id = None

    def _animate(self, frm, to):
        fx, fy = self._parse_pos(frm)
        tx, ty = self._parse_pos(to)
        step_ms = max(1, self.SLIDE_MS // self.SLIDE_STEPS)

        def step(i):
            if not self.root:
                return
            frac = i / self.SLIDE_STEPS
            x = int(fx + (tx - fx) * frac)
            y = int(fy + (ty - fy) * frac)
            self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")
            if i < self.SLIDE_STEPS:
                self.root.after(step_ms, lambda: step(i + 1))

        step(1)

    @staticmethod
    def _parse_pos(geom):
        # "WxH+X+Y" -> (X, Y)
        try:
            _, pos = geom.split("+", 1)
            x_str, y_str = pos.split("+")
            return int(x_str), int(y_str)
        except Exception:
            return 0, 0
```

- [ ] **Step 2: Commit**

```
git add views/autohide.py
git commit -m "feat: add Autohide view with edge-slide animation"
```

---

## Task 12: Entry point rewrite

**Files:**
- Modify: `claude_monitor.py` (full rewrite — old code is now distributed across modules)

- [ ] **Step 1: Replace `claude_monitor.py` with the new entry point**

```python
"""Claude Usage Monitor — entry point.

Loads config, wires up ModeManager + Poller + UsageClient, starts the chosen view.
"""

import argparse
import sys
from pathlib import Path

from config import Config, VALID_MODES
from i18n import set_language
from mode_manager import ModeManager
from poller import Poller
from usage_client import UsageClient
from views.autohide import AutohideView
from views.cli import CLIView
from views.overlay import OverlayView
from views.tray import TrayView

CFG_PATH = Path(__file__).parent / "config.ini"


def parse_args():
    ap = argparse.ArgumentParser(description="Claude Usage Monitor")
    ap.add_argument("--mode", choices=VALID_MODES, help="Override starting mode (config.ini default if unset)")
    ap.add_argument("--no-save-mode", action="store_true",
                    help="Don't persist mode changes back to config.ini")
    return ap.parse_args()


def main():
    args = parse_args()

    if not CFG_PATH.exists():
        print(f"Missing {CFG_PATH}. Copy config.ini.example and fill in cookies + org_id.")
        sys.exit(1)

    cfg = Config.load(CFG_PATH)
    if not cfg.cookies:
        print("Set 'cookies' under [claude] in config.ini")
        sys.exit(1)
    if not cfg.org_id:
        print("Set 'org_id' under [claude] in config.ini")
        sys.exit(1)

    set_language(cfg.language)
    start_mode = args.mode or cfg.mode

    client = UsageClient(org_id=cfg.org_id, cookies=cfg.cookies)
    mgr = ModeManager(
        cfg_path=CFG_PATH,
        view_factories={
            "overlay":  OverlayView,
            "tray":     TrayView,
            "cli":      CLIView,
            "autohide": AutohideView,
        },
        poller=None,  # set below
        save_mode=not args.no_save_mode,
    )
    # Expose cfg to views that need it (Autohide reads autohide_* fields)
    mgr.config = cfg

    poller = Poller(client, interval=cfg.poll_interval, on_data=mgr.on_poll_data)
    mgr.poller = poller

    poller.start()
    mgr.start_initial(start_mode)
    try:
        mgr.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test — overlay mode**

Run: `python claude_monitor.py`
Expected: floating overlay appears in bottom-right. Right-click → "Switch mode" submenu shows 4 options. Quit closes cleanly.

- [ ] **Step 3: Smoke test — tray mode**

Run: `python claude_monitor.py --mode tray`
Expected: tray icon appears in notification area with color+number. Hover shows the 5-line tooltip. Left-click toggles a popup panel. Right-click shows menu. Selecting "Switch mode → Overlay" replaces tray with overlay.

- [ ] **Step 4: Smoke test — cli mode**

Run: `python claude_monitor.py --mode cli`
Expected: single ANSI line in the terminal, redrawn every poll. Typing `q` + Enter quits cleanly.

- [ ] **Step 5: Smoke test — autohide mode**

Run: `python claude_monitor.py --mode autohide`
Expected: window appears as a 3px sliver on the right edge. Hovering reveals it via a smooth slide-in. Mouse-out → window slides back after ~1.5s. Right-click → "Force show" pins it open.

- [ ] **Step 6: Smoke test — mode persistence**

Steps:
1. `python claude_monitor.py` (starts in overlay, the default)
2. Right-click → Switch mode → Tray. Confirm tray appears.
3. Quit via right-click → Quit.
4. Re-run `python claude_monitor.py` (no `--mode`).
5. Expected: starts in tray (last selected).
6. Open `config.ini` and confirm `[ui] mode = tray`.

- [ ] **Step 7: Smoke test — `--no-save-mode`**

Steps:
1. Manually set `config.ini` `mode = overlay`.
2. `python claude_monitor.py --mode tray --no-save-mode`
3. Switch to autohide via menu. Quit.
4. Open `config.ini`. Expected: `mode = overlay` (unchanged).

- [ ] **Step 8: Smoke test — CLI requires console**

Steps:
1. `pythonw.exe claude_monitor.py --mode cli`
2. Expected: process exits (no usable stdout). Alternatively, start overlay then try menu → Switch mode → CLI; expect the error messagebox: *"CLI mode requires python.exe..."* and mode unchanged.

- [ ] **Step 9: Commit**

```
git add claude_monitor.py
git commit -m "feat: rewrite entry point as ModeManager bootstrap with argparse"
```

---

## Task 13: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README features list**

In `README.md`, replace the `## Features` block to include the new modes. Locate the bullet list starting with `🟢 5-hour session ...` and replace the bullets with:

```markdown
- 🟢 **5-hour session** — current session utilization (%) with a live reset countdown
- 📅 **Weekly usage** — rolling 7-day utilization and reset timer
- 🤖 **Per-model breakdown** — separate 7-day Sonnet utilization
- 💳 **Extra credits** — additional credit usage against your monthly limit
- 🎨 **Status colors** — green (<60%) → yellow (<85%) → red (85%+)
- 🪟 **4 display modes** — Overlay (floating), Tray (notification area), CLI (single-line terminal), Autohide (edge-docked, slide on hover) — switchable at runtime via right-click menu
- 🖱 **Drag to reposition / right-click menu** — refresh / switch mode / quit
- ☁️ **Cloudflare-friendly** — uses `curl_cffi` browser impersonation to bypass challenges
- 🔒 **Credentials separated** — cookies and org ID live in a gitignored `config.ini`
```

- [ ] **Step 2: Update Installation block**

Replace the `pip install curl_cffi` line with:

```bash
pip install curl_cffi pystray Pillow
```

And add below it:

> `pystray` + `Pillow` enable the Tray mode. `tkinter` ships with the official Python for Windows installer.

- [ ] **Step 3: Add Display Modes section**

Insert this section after `## Configuration` and before `## Usage`:

```markdown
## Display Modes

The monitor supports four interchangeable modes. The active mode is saved in `config.ini` (`[ui] mode = ...`) and can be switched at runtime from the right-click menu.

| Mode | What it looks like | When to use |
|---|---|---|
| `overlay` (default) | Small always-on-top floating panel in the bottom-right corner | You want the numbers visible at all times. |
| `tray` | Color-coded icon with % in the Windows notification area; left-click for popup; hover for tooltip | You don't want the desktop covered. Glance occasionally. |
| `cli` | Single ANSI-colored line in your terminal, redrawn every poll | You live in a terminal anyway. Press `q` + Enter to quit. |
| `autohide` | Floating window docked to a screen edge; only a 3px peek strip is visible; hover to slide in | You want zero permanent visual footprint but instant access. |

Override the mode at launch with `--mode <name>` (e.g., `python claude_monitor.py --mode tray`). Use `--no-save-mode` to prevent runtime switches from being persisted to `config.ini`.

> **CLI mode** requires a visible console — run with `python.exe`, not `pythonw.exe`. Switching to CLI from another mode is blocked (with a message) if no console is attached.
```

- [ ] **Step 4: Update FAQ — replace the "Resize / different size?" entry if it exists, otherwise add a new entry**

Append this FAQ entry to the existing `<details>` blocks:

```markdown
<details>
<summary><b>The tray icon shows the wrong number / wrong color.</b></summary>

The tray icon updates each poll cycle (default 60s). The 5-hour session percentage is what's displayed. If you just hit a threshold, wait one cycle, or use the right-click menu → "Refresh now."
</details>
```

- [ ] **Step 5: Commit**

```
git add README.md
git commit -m "docs: document four display modes and new dependencies"
```

---

## Final Verification

- [ ] **Step 1: Full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass across `test_config.py`, `test_usage_client.py`, `test_poller.py`, `test_mode_manager.py`.

- [ ] **Step 2: Full manual matrix**

For each pair from {overlay, tray, autohide} (CLI is one-way), confirm runtime switching works:

| From → To | Expected |
|---|---|
| overlay → tray | overlay window closes; tray icon appears |
| overlay → autohide | overlay disappears; window docks to right edge |
| tray → overlay | tray icon removed; overlay appears |
| tray → autohide | tray removed; docked window appears |
| autohide → overlay | docked window replaced by free-floating overlay |
| autohide → tray | docked window removed; tray icon appears |
| overlay → cli | overlay closes; terminal shows single ANSI line (only if console attached) |
| tray → cli | tray removes; CLI starts (console attached) |
| autohide → cli | docked window removes; CLI starts (console attached) |

- [ ] **Step 3: Persistence check**

1. Start fresh: `mode = overlay` in `config.ini`.
2. Switch through `tray → autohide → overlay`.
3. Quit, restart with no flags.
4. Confirm starts in `overlay` (the last saved mode).
5. Open `config.ini` and confirm `[ui] mode = overlay`.

- [ ] **Step 4: Push branch and open PR**

```
git push -u origin feature/multi-mode-display
gh pr create --title "feat: multi-mode display (overlay/tray/cli/autohide)" --body-file docs/superpowers/specs/2026-05-14-multi-mode-display-design.md
```

(If `gh` is not installed or repository is local-only, skip the PR step.)
