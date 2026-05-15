# Tray + Overlay Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the tray icon to display alongside the overlay (or autohide) view as a "companion" subsystem, controlled by config + runtime menu toggle, persisted under the existing `--no-save-mode` rule.

**Architecture:** Extend `ModeManager` with a second `current_companion: Optional[View]` slot. A single `_should_show_companion(mode, flag)` decides activation. The companion `TrayView` borrows the main view's `tk.Tk()` root instead of creating its own. Spec: `docs/superpowers/specs/2026-05-15-tray-overlay-companion-design.md`.

**Tech Stack:** Python 3, Tkinter, pystray, Pillow. Existing `pytest` test framework. Windows 10/11 only.

---

## File map

- **Modify** `config.py` — add `tray_companion` field + `save_tray_companion` helper (refactor shared INI patcher)
- **Modify** `mode_manager.py` — add companion slot, `_should_show_companion`, `_sync_companion`, `request_toggle_companion`, `request_focus_main_view`, fan-out in `on_poll_data`
- **Modify** `views/base.py` — add `focus()` no-op default
- **Modify** `views/overlay.py` — implement `focus()`, add tray-companion toggle to right-click menu
- **Modify** `views/autohide.py` — implement `focus()` (force-show on), add tray-companion toggle to right-click menu
- **Modify** `views/tray.py` — add `companion=True` ctor flag (borrowed root, focus-main on left-click, "Turn off tray companion" menu item)
- **Modify** `claude_monitor.py` — wire `companion_factories`, `save_tray_companion`, `initial_companion_flag` into `ModeManager`
- **Modify** `i18n.py` — add `menu_tray_companion`, `menu_companion_off`
- **Modify** `config.ini.example` — document new key
- **Modify** `tests/test_config.py` — load + save round-trips for `tray_companion`
- **Modify** `tests/test_mode_manager.py` — companion lifecycle, fan-out, persistence rules

---

## Task 1: Refactor `save_mode` into a shared INI key patcher

**Why first:** `save_tray_companion` will need the same line-based patcher logic. Extracting it now keeps both helpers DRY.

**Files:**
- Modify: `config.py:47-101`
- Test: `tests/test_config.py` (existing tests must still pass)

- [ ] **Step 1: Read current `save_mode` in `config.py:47-101`** to understand the patcher

- [ ] **Step 2: Run existing config tests to confirm they're green**

```
pytest tests/test_config.py -v
```
Expected: all pass.

- [ ] **Step 3: Extract `_set_ini_key` from `save_mode`. Replace `save_mode` body to delegate.**

```python
# config.py — replace save_mode and add _set_ini_key

def save_mode(path: Path, mode: str):
    """Persist [ui] mode = <mode>, preserving comments and ordering."""
    _set_ini_key(Path(path), section="ui", key="mode", value=mode)


def _set_ini_key(path: Path, section: str, key: str, value: str):
    """Rewrite [section] key = <value> in-place, preserving comments and ordering.

    configparser's write() would clobber inline comments, so we patch the file
    line-by-line. If [section] or `key` does not exist, append them.
    """
    if not path.exists():
        path.write_text(f"[{section}]\n{key} = {value}\n", encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_section = False
    section_seen = False
    key_written = False
    out = []

    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    key_re = re.compile(rf"^(\s*{re.escape(key)}\s*=[^\S\n]*)(\S*)(.*)$")

    for line in lines:
        sec = section_re.match(line)
        if sec:
            if in_section and not key_written:
                out.append(f"{key} = {value}\n")
                key_written = True
            in_section = sec.group(1).strip().lower() == section.lower()
            if in_section:
                section_seen = True
            out.append(line)
            continue

        if in_section and not key_written:
            m = key_re.match(line)
            if m:
                prefix, _old, tail = m.groups()
                out.append(f"{prefix}{value}{tail}\n" if not tail.endswith("\n") else f"{prefix}{value}{tail}")
                key_written = True
                continue
        out.append(line)

    if in_section and not key_written:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key} = {value}\n")
        key_written = True
    elif not section_seen:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"\n[{section}]\n")
        out.append(f"{key} = {value}\n")

    path.write_text("".join(out), encoding="utf-8")
```

- [ ] **Step 4: Re-run existing config tests**

```
pytest tests/test_config.py -v
```
Expected: all pass (refactor is behavior-preserving).

- [ ] **Step 5: Commit**

```
git add config.py
git commit -m "refactor: extract _set_ini_key helper from save_mode"
```

---

## Task 2: Add `Config.tray_companion` field

**Files:**
- Modify: `config.py:11-44`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_config.py`)

```python
def test_tray_companion_defaults_false_when_missing(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\n", encoding="utf-8")
    cfg = Config.load(p)
    assert cfg.tray_companion is False


def test_tray_companion_loads_true(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text(
        "[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\ntray_companion = true\n",
        encoding="utf-8",
    )
    cfg = Config.load(p)
    assert cfg.tray_companion is True


def test_tray_companion_loads_false_explicit(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text(
        "[claude]\ncookies=a\norg_id=b\n[ui]\nmode = overlay\ntray_companion = false\n",
        encoding="utf-8",
    )
    cfg = Config.load(p)
    assert cfg.tray_companion is False
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/test_config.py::test_tray_companion_defaults_false_when_missing tests/test_config.py::test_tray_companion_loads_true tests/test_config.py::test_tray_companion_loads_false_explicit -v
```
Expected: AttributeError or missing-field failures.

- [ ] **Step 3: Add the field to `Config` and `Config.load`**

In `config.py`, add field to the dataclass:
```python
@dataclass
class Config:
    cookies: str
    org_id: str
    poll_interval: int
    language: str
    mode: str
    tray_companion: bool         # NEW
    tray_popup_position: str
    autohide_edge: str
    autohide_peek_pixels: int
    autohide_slide_ms: int
    autohide_hide_delay_ms: int
```

And populate it in `load`:
```python
        return cls(
            cookies=cp.get("claude", "cookies", fallback=""),
            org_id=cp.get("claude", "org_id", fallback=""),
            poll_interval=cp.getint("claude", "poll_interval", fallback=60),
            language=cp.get("ui", "language", fallback="en").strip().lower(),
            mode=mode,
            tray_companion=cp.getboolean("ui", "tray_companion", fallback=False),
            tray_popup_position=cp.get("tray", "popup_position", fallback="above"),
            autohide_edge=cp.get("autohide", "edge", fallback="bottom"),
            autohide_peek_pixels=cp.getint("autohide", "peek_pixels", fallback=3),
            autohide_slide_ms=cp.getint("autohide", "slide_ms", fallback=110),
            autohide_hide_delay_ms=cp.getint("autohide", "hide_delay_ms", fallback=1500),
        )
```

- [ ] **Step 4: Re-run tests — expect pass**

```
pytest tests/test_config.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add config.py tests/test_config.py
git commit -m "feat(config): add tray_companion bool field with default false"
```

---

## Task 3: Add `save_tray_companion` helper

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
def test_save_tray_companion_round_trip(cfg_file):
    from config import save_tray_companion
    save_tray_companion(cfg_file, True)
    cfg = Config.load(cfg_file)
    assert cfg.tray_companion is True
    save_tray_companion(cfg_file, False)
    cfg = Config.load(cfg_file)
    assert cfg.tray_companion is False


def test_save_tray_companion_preserves_mode_and_comments(cfg_file):
    from config import save_tray_companion
    save_tray_companion(cfg_file, True)
    text = cfg_file.read_text(encoding="utf-8")
    assert "tray_companion = true" in text
    assert "; overlay | tray | cli | autohide" in text  # comment on mode line preserved
    assert "language = ko" in text


def test_save_tray_companion_adds_section_if_missing(tmp_path):
    from config import save_tray_companion
    p = tmp_path / "c.ini"
    p.write_text("[claude]\ncookies=a\norg_id=b\n", encoding="utf-8")
    save_tray_companion(p, True)
    text = p.read_text(encoding="utf-8")
    assert "[ui]" in text
    assert "tray_companion = true" in text
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/test_config.py::test_save_tray_companion_round_trip tests/test_config.py::test_save_tray_companion_preserves_mode_and_comments tests/test_config.py::test_save_tray_companion_adds_section_if_missing -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `save_tray_companion` using `_set_ini_key`**

Append to `config.py`:
```python
def save_tray_companion(path: Path, value: bool):
    """Persist [ui] tray_companion = <true|false>."""
    _set_ini_key(Path(path), section="ui", key="tray_companion", value="true" if value else "false")
```

- [ ] **Step 4: Re-run tests**

```
pytest tests/test_config.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add config.py tests/test_config.py
git commit -m "feat(config): add save_tray_companion helper"
```

---

## Task 4: Add i18n keys

**Files:**
- Modify: `i18n.py`

- [ ] **Step 1: Add keys to both `en` and `ko` dicts**

In `i18n.py` `TRANSLATIONS["en"]`, add:
```python
        "menu_tray_companion":   "Show tray icon",
        "menu_companion_off":    "Turn off tray companion",
```

In `TRANSLATIONS["ko"]`, add:
```python
        "menu_tray_companion":   "트레이 함께 표시",
        "menu_companion_off":    "트레이 컴패니언 끄기",
```

- [ ] **Step 2: Verify both languages have all the same keys**

Eyeball it; both dicts should contain `menu_tray_companion` and `menu_companion_off`.

- [ ] **Step 3: Commit**

```
git add i18n.py
git commit -m "feat(i18n): add tray companion menu strings"
```

---

## Task 5: Add `_should_show_companion` to `ModeManager`

**Files:**
- Modify: `mode_manager.py`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_mode_manager.py`)

```python
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
```

- [ ] **Step 2: Run — expect failure**

```
pytest tests/test_mode_manager.py::test_should_show_companion_truth_table -v
```
Expected: AttributeError on `tray_companion` or `_should_show_companion`.

- [ ] **Step 3: Add the field and method**

Edit `ModeManager.__init__` to add the field with safe default:
```python
    def __init__(
        self,
        cfg_path: Path,
        view_factories: Dict[str, Callable],
        poller,
        save_mode: bool,
        companion_factories: Optional[Dict[str, Callable]] = None,
        save_tray_companion: Optional[Callable] = None,
        initial_companion_flag: bool = False,
    ):
        self.cfg_path = Path(cfg_path)
        self.view_factories = view_factories
        self.companion_factories = companion_factories or {}
        self.poller = poller
        self.save_mode = save_mode
        self.save_tray_companion = save_tray_companion
        self.tray_companion = bool(initial_companion_flag)

        self.current_mode: Optional[str] = None
        self.current_view = None
        self.current_companion: Optional["View"] = None
        self.last_data = None
        self._quit_requested = False
        self._pending_switch: Optional[str] = None
```

Add the method (anywhere after `__init__`):
```python
    def _should_show_companion(self) -> bool:
        return self.tray_companion and self.current_mode in ("overlay", "autohide")
```

- [ ] **Step 4: Re-run tests**

```
pytest tests/test_mode_manager.py -v
```
Expected: all pass (existing tests use defaults, so they still work).

- [ ] **Step 5: Commit**

```
git add mode_manager.py tests/test_mode_manager.py
git commit -m "feat(mode_manager): add companion slot + _should_show_companion"
```

---

## Task 6: `_sync_companion` + `request_toggle_companion`

**Files:**
- Modify: `mode_manager.py`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/test_mode_manager.py::test_sync_companion_starts_when_compatible tests/test_mode_manager.py::test_sync_companion_skips_when_incompatible tests/test_mode_manager.py::test_sync_companion_stops_existing_when_no_longer_needed tests/test_mode_manager.py::test_request_toggle_companion_persists_when_save_mode_on tests/test_mode_manager.py::test_request_toggle_companion_skips_save_when_no_save_mode -v
```
Expected: AttributeError.

- [ ] **Step 3: Implement `_sync_companion` and `request_toggle_companion`**

Add to `ModeManager`:
```python
    def _sync_companion(self):
        """Idempotent: brings current_companion into agreement with _should_show_companion()."""
        want = self._should_show_companion()
        if want and self.current_companion is None:
            factory = self.companion_factories.get("tray")
            if factory is None:
                return
            self.current_companion = factory(self)
            try:
                self.current_companion.start(self.last_data)
            except Exception as e:
                print(f"[companion start error] {e}")
                self.current_companion = None
        elif not want and self.current_companion is not None:
            try:
                self.current_companion.stop()
            except Exception as e:
                print(f"[companion stop error] {e}")
            self.current_companion = None

    def request_toggle_companion(self, on: bool):
        self.tray_companion = bool(on)
        if self.save_mode and self.save_tray_companion is not None:
            try:
                self.save_tray_companion(self.cfg_path, self.tray_companion)
            except Exception as e:
                print(f"[companion save error] {e}")
        self._sync_companion()
```

- [ ] **Step 4: Re-run tests**

```
pytest tests/test_mode_manager.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add mode_manager.py tests/test_mode_manager.py
git commit -m "feat(mode_manager): add _sync_companion + request_toggle_companion"
```

---

## Task 7: Fan-out `on_poll_data` to companion

**Files:**
- Modify: `mode_manager.py:64-83`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing tests**

```python
def test_on_poll_data_fans_out_to_companion(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    # start_initial doesn't auto-sync companion until Task 8 wires it in,
    # so set up companion explicitly here.
    mgr.start_initial("overlay")
    mgr.current_mode = "overlay"
    mgr._sync_companion()
    assert mgr.current_companion is not None  # sanity from Task 6
    mgr.on_poll_data("D1")
    assert mgr.current_view.updates == ["D1"]
    assert mgr.current_companion.updates == ["D1"]
```

- [ ] **Step 2: Run — expect failure**

```
pytest tests/test_mode_manager.py::test_on_poll_data_fans_out_to_companion -v
```
Expected: companion.updates is empty.

- [ ] **Step 3: Refactor `on_poll_data` to fan out**

Replace the body (`mode_manager.py:64-83`) with:
```python
    def on_poll_data(self, data):
        self.last_data = data
        for view in (self.current_view, self.current_companion):
            self._dispatch_to_view(view, data)

    def _dispatch_to_view(self, view, data):
        if view is None:
            return
        root = getattr(view, "root", None)
        if root is not None:
            try:
                root.after(0, lambda v=view: v.on_update(data) if v in (self.current_view, self.current_companion) else None)
            except Exception:
                pass
            return
        if view in (self.current_view, self.current_companion):
            view.on_update(data)
```

- [ ] **Step 4: Re-run tests**

```
pytest tests/test_mode_manager.py -v
```
Expected: all pass (including the existing fan-out + stale-callback tests, which still cover the main view's path).

- [ ] **Step 5: Commit**

```
git add mode_manager.py tests/test_mode_manager.py
git commit -m "feat(mode_manager): fan out poll data to companion view"
```

---

## Task 8: Wire `_sync_companion` into `start_initial`, `_do_switch`, and `run` cleanup

**Files:**
- Modify: `mode_manager.py`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing tests**

```python
def test_start_initial_creates_companion(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.start_initial("overlay")
    assert mgr.current_companion is not None
    assert mgr.current_companion.started


def test_switch_overlay_to_autohide_keeps_companion(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.start_initial("overlay")
    old_companion = mgr.current_companion
    mgr._do_switch("autohide")
    # Companion is recreated (bound to new root), not preserved verbatim.
    assert old_companion.stopped
    assert mgr.current_companion is not None
    assert mgr.current_companion is not old_companion
    assert mgr.current_companion.started


def test_switch_overlay_to_cli_stops_companion(tmp_path):
    mgr, _ = _make_mgr(
        tmp_path,
        companion_factories={"tray": FakeView},
        initial_companion_flag=True,
    )
    mgr.start_initial("overlay")
    mgr._do_switch("cli")
    assert mgr.current_companion is None
```

- [ ] **Step 2: Run — expect failures**

```
pytest tests/test_mode_manager.py::test_start_initial_creates_companion tests/test_mode_manager.py::test_switch_overlay_to_autohide_keeps_companion tests/test_mode_manager.py::test_switch_overlay_to_cli_stops_companion -v
```
Expected: companion not created / not stopped at the right moments.

- [ ] **Step 3: Wire `_sync_companion` into the lifecycle**

Edit `start_initial` (`mode_manager.py:30-35`):
```python
    def start_initial(self, mode: str):
        if mode not in self.view_factories:
            mode = "overlay"
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)
        self._sync_companion()
```

Edit `_do_switch` (`mode_manager.py:106-118`):
```python
    def _do_switch(self, mode: str):
        if self.save_mode:
            try:
                cfg_save_mode(self.cfg_path, mode)
            except Exception as e:
                print(f"[mode save error] {e}")
        # Stop the companion first so its borrowed root reference is released
        # before the main view (which owns the root) is destroyed.
        if self.current_companion:
            try:
                self.current_companion.stop()
            except Exception as e:
                print(f"[companion stop error] {e}")
            self.current_companion = None
        if self.current_view:
            self.current_view.stop()
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)
        self._sync_companion()
```

Edit `run` cleanup tail (`mode_manager.py:56-60`):
```python
        # Cleanup on quit
        if self.current_companion:
            try:
                self.current_companion.stop()
            except Exception:
                pass
            self.current_companion = None
        if self.current_view:
            self.current_view.stop()
        if self.poller:
            self.poller.stop()
```

- [ ] **Step 4: Re-run all mode_manager tests**

```
pytest tests/test_mode_manager.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add mode_manager.py tests/test_mode_manager.py
git commit -m "feat(mode_manager): sync companion across start, switch, quit"
```

---

## Task 9: Add `View.focus()` no-op + `request_focus_main_view`

**Files:**
- Modify: `views/base.py`
- Modify: `mode_manager.py`
- Test: `tests/test_mode_manager.py`

- [ ] **Step 1: Write failing test**

```python
def test_request_focus_main_view_calls_focus_on_current(tmp_path):
    class FocusView(FakeView):
        def __init__(self, manager):
            super().__init__(manager)
            self.focused = 0
        def focus(self):
            self.focused += 1

    mgr, _ = _make_mgr(
        tmp_path,
        view_factories={"overlay": FocusView, "tray": FocusView, "cli": FocusView, "autohide": FocusView},
    )
    mgr.start_initial("overlay")
    mgr.request_focus_main_view()
    assert mgr.current_view.focused == 1


def test_request_focus_main_view_safe_when_no_focus_method(tmp_path):
    mgr, _ = _make_mgr(tmp_path)
    mgr.start_initial("overlay")
    # FakeView has no focus(); should not raise.
    mgr.request_focus_main_view()
```

- [ ] **Step 2: Run — expect failure**

```
pytest tests/test_mode_manager.py::test_request_focus_main_view_calls_focus_on_current tests/test_mode_manager.py::test_request_focus_main_view_safe_when_no_focus_method -v
```
Expected: AttributeError on `request_focus_main_view`.

- [ ] **Step 3: Add `focus` to base `View`**

Edit `views/base.py`:
```python
class View(ABC):
    """A display surface. Owns its UI lifecycle; receives usage updates via on_update."""

    def __init__(self, manager):
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

    def focus(self) -> None:
        """Bring this view to the foreground. Default: no-op. Override for focusable views."""
```

- [ ] **Step 4: Add `request_focus_main_view` to `ModeManager`**

```python
    def request_focus_main_view(self):
        view = self.current_view
        if view is None:
            return
        focus = getattr(view, "focus", None)
        if callable(focus):
            try:
                focus()
            except Exception as e:
                print(f"[focus error] {e}")
```

- [ ] **Step 5: Re-run tests**

```
pytest tests/test_mode_manager.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add views/base.py mode_manager.py tests/test_mode_manager.py
git commit -m "feat: add View.focus() and ModeManager.request_focus_main_view"
```

---

## Task 10: Implement `OverlayView.focus()`

**Files:**
- Modify: `views/overlay.py`

- [ ] **Step 1: Add the method to `OverlayView`** (anywhere after `_show_menu`):

```python
    def focus(self) -> None:
        if not self.root:
            return
        try:
            self.root.attributes("-topmost", False)
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
```

- [ ] **Step 2: Run all tests to confirm no regressions**

```
pytest -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```
git add views/overlay.py
git commit -m "feat(overlay): implement focus() to lift and focus the window"
```

---

## Task 11: Implement `AutohideView.focus()`

**Files:**
- Modify: `views/autohide.py`

- [ ] **Step 1: Add the method to `AutohideView`** (anywhere after `_toggle_force_show`):

```python
    def focus(self) -> None:
        """Companion left-click: ensure the docked panel is visible.

        If not already force-shown, slide in and lock open. Caller can later
        toggle force-show off via the right-click menu.
        """
        if not self.root:
            return
        try:
            if not self._force_show:
                self._force_show = True
                if self._force_show_var is not None:
                    self._force_show_var.set(True)
                self._slide_in(force=True)
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
```

- [ ] **Step 2: Run all tests**

```
pytest -v
```
Expected: all pass (no autohide-specific tests touch focus).

- [ ] **Step 3: Commit**

```
git add views/autohide.py
git commit -m "feat(autohide): implement focus() — force-show on demand"
```

---

## Task 12: TrayView companion mode (constructor + borrowed root)

**Files:**
- Modify: `views/tray.py`

- [ ] **Step 1: Update `TrayView.__init__`** to accept `companion`:

```python
class TrayView(View):
    def __init__(self, manager, *, companion: bool = False):
        super().__init__(manager)
        self.companion = companion
        self.icon: Optional[pystray.Icon] = None
        self._popup: Optional[tk.Toplevel] = None
        self._last: Optional[UsageData] = None
        self._tk_root: Optional[tk.Tk] = None
        self._owns_root: bool = False
        self._stop = threading.Event()
        self._tk_queue: "queue.Queue" = queue.Queue()
```

- [ ] **Step 2: Update `start()` to borrow the main view's root in companion mode**

Replace `start` (`views/tray.py:95-107`):
```python
    def start(self, initial: Optional[UsageData]) -> None:
        self._last = initial
        if self.companion:
            # Borrow the main view's root so we don't fight Tkinter over a second tk.Tk()
            # and so messageboxes/Toplevels parent correctly.
            main_view = getattr(self.manager, "current_view", None)
            borrowed = getattr(main_view, "root", None) if main_view else None
            if borrowed is None:
                # Defensive: fall back to owning a hidden root (worst case: dual roots,
                # same as standalone).
                self._tk_root = tk.Tk()
                self._tk_root.withdraw()
                self._owns_root = True
            else:
                self._tk_root = borrowed
                self._owns_root = False
        else:
            self._tk_root = tk.Tk()
            self._tk_root.withdraw()
            self._owns_root = True

        self.icon = pystray.Icon(
            "claude_monitor",
            icon=make_icon_image(initial.five_hour_pct if initial else None),
            title=make_tooltip(initial),
            menu=self._build_menu(),
        )
        threading.Thread(target=self.icon.run, daemon=True).start()
```

- [ ] **Step 3: Adjust `run_mainloop` so companion mode does NOT pump Tk**

The companion isn't the main view; the main view drives the loop. Replace `run_mainloop` (`views/tray.py:109-122`):
```python
    def run_mainloop(self):
        if self.companion:
            # The main view drives the Tk loop. Pump our queue via root.after.
            # Schedule a drain tick so cross-thread work still flows.
            self._schedule_companion_drain()
            return
        # Standalone: pump Tk + drain queue ourselves.
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
        self._teardown_tk()

    def _schedule_companion_drain(self):
        if self._tk_root is None or self._stop.is_set():
            return
        try:
            self._drain_queue()
        except Exception as e:
            print(f"[tray companion drain error] {e}")
        try:
            self._tk_root.after(50, self._schedule_companion_drain)
        except Exception:
            pass
```

- [ ] **Step 4: Adjust `stop()` to only tear down Tk when we own it**

Replace `stop` (`views/tray.py:139-149`) with:
```python
    def stop(self) -> None:
        self._stop.set()
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
        if self.companion:
            # We do not own the root; just drop the popup if any (must run on Tk thread).
            if self._popup is not None and self._tk_root is not None:
                try:
                    self._popup.destroy()
                except Exception:
                    pass
                self._popup = None
            # Drop the borrowed reference; do NOT destroy.
            self._tk_root = None
```

(The standalone `_teardown_tk` path stays untouched — it runs from `run_mainloop` after the loop exits.)

- [ ] **Step 5: Run unit tests** (no Tk required for the companion path; just sanity-check)

```
pytest -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add views/tray.py
git commit -m "feat(tray): support companion mode with borrowed Tk root"
```

---

## Task 13: TrayView companion menu + left-click behavior

**Files:**
- Modify: `views/tray.py`

- [ ] **Step 1: Update `_build_menu`** to vary by mode:

```python
    def _build_menu(self):
        items = [
            pystray.MenuItem(T("menu_switch_mode"), pystray.Menu(
                pystray.MenuItem(T("mode_overlay"),  lambda: self.manager.request_switch("overlay")),
                pystray.MenuItem(T("mode_tray"),     lambda: None, enabled=False),
                pystray.MenuItem(T("mode_autohide"), lambda: self.manager.request_switch("autohide")),
            )),
            pystray.MenuItem(T("menu_refresh"), lambda: self.manager.request_refresh()),
            pystray.MenuItem(T("menu_tray_settings"), lambda: self._open_tray_settings()),
        ]
        if self.companion:
            items.append(
                pystray.MenuItem(T("menu_companion_off"),
                                 lambda: self.manager.request_toggle_companion(False))
            )
        items.append(pystray.MenuItem(T("menu_quit"), lambda: self.manager.request_quit()))
        items.append(pystray.MenuItem("show", self._on_left_click, default=True, visible=False))
        return pystray.Menu(*items)
```

- [ ] **Step 2: Update `_on_left_click` / `_toggle_popup` to focus main view in companion mode**

Replace `_on_left_click` (`views/tray.py:210-212`) and `_toggle_popup` (`views/tray.py:214-222`):
```python
    def _on_left_click(self, icon, item):
        # pystray callback (pystray thread) — defer to the Tk main thread.
        self._post(self._handle_left_click)

    def _handle_left_click(self):
        if self.companion:
            self.manager.request_focus_main_view()
            return
        self._toggle_popup()
```

- [ ] **Step 3: Run all tests**

```
pytest -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```
git add views/tray.py
git commit -m "feat(tray): companion menu adds 'turn off'; left-click focuses main"
```

---

## Task 14: OverlayView "Tray companion" menu item

**Files:**
- Modify: `views/overlay.py:186-199`

- [ ] **Step 1: Add the toggle to `_show_menu`**

Insert the toggle between Refresh and Quit. Replace `_show_menu`:

```python
    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        switch = tk.Menu(menu, tearoff=0, bg="#2C2C2E", fg="white",
                         activebackground="#3A3A3C", activeforeground="white")
        switch.add_command(label=T("mode_overlay"),  command=lambda: self.manager.request_switch("overlay"))
        switch.add_command(label=T("mode_tray"),     command=lambda: self.manager.request_switch("tray"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        # Tray companion toggle — glyph reflects current state to avoid Tk variable lifetime issues.
        glyph = "☑" if getattr(self.manager, "tray_companion", False) else "☐"
        menu.add_command(
            label=f"{glyph} {T('menu_tray_companion')}",
            command=lambda: self.manager.request_toggle_companion(not self.manager.tray_companion),
        )
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)
```

- [ ] **Step 2: Run tests**

```
pytest -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```
git add views/overlay.py
git commit -m "feat(overlay): add tray companion toggle to right-click menu"
```

---

## Task 15: AutohideView "Tray companion" menu item

**Files:**
- Modify: `views/autohide.py:133-150`

- [ ] **Step 1: Add the toggle to `_show_menu`**

Replace `_show_menu`:

```python
    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        switch = tk.Menu(menu, tearoff=0, bg="#2C2C2E", fg="white",
                         activebackground="#3A3A3C", activeforeground="white")
        switch.add_command(label=T("mode_overlay"),  command=lambda: self.manager.request_switch("overlay"))
        switch.add_command(label=T("mode_tray"),     command=lambda: self.manager.request_switch("tray"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        self._force_show_var.set(self._force_show)
        menu.add_checkbutton(label=T("menu_force_show"),
                             command=self._toggle_force_show,
                             variable=self._force_show_var)
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        glyph = "☑" if getattr(self.manager, "tray_companion", False) else "☐"
        menu.add_command(
            label=f"{glyph} {T('menu_tray_companion')}",
            command=lambda: self.manager.request_toggle_companion(not self.manager.tray_companion),
        )
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)
```

- [ ] **Step 2: Run tests**

```
pytest -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```
git add views/autohide.py
git commit -m "feat(autohide): add tray companion toggle to right-click menu"
```

---

## Task 16: Wire entry point

**Files:**
- Modify: `claude_monitor.py:86-105`

- [ ] **Step 1: Update import + ModeManager construction**

Top of `claude_monitor.py`, add to imports:
```python
from config import Config, VALID_MODES, save_tray_companion
```

Edit the `ModeManager(...)` call (`claude_monitor.py:87-99`):
```python
    mgr = ModeManager(
        cfg_path=CFG_PATH,
        view_factories={
            "overlay":  OverlayView,
            "tray":     TrayView,
            "cli":      CLIView,
            "autohide": AutohideView,
        },
        companion_factories={
            "tray": lambda m: TrayView(m, companion=True),
        },
        poller=None,  # set below
        save_mode=not args.no_save_mode,
        save_tray_companion=save_tray_companion,
        initial_companion_flag=cfg.tray_companion,
    )
```

- [ ] **Step 2: Run all tests + smoke-import**

```
pytest -v
python -c "import claude_monitor"
```
Expected: tests pass, no import errors.

- [ ] **Step 3: Commit**

```
git add claude_monitor.py
git commit -m "feat(entry): wire tray companion factory + flag into ModeManager"
```

---

## Task 17: Update `config.ini.example`

**Files:**
- Modify: `config.ini.example`

- [ ] **Step 1: Add the new key under `[ui]`**

Replace the `[ui]` block:
```ini
[ui]
language       = en              ; en | ko
mode           = overlay         ; overlay | tray | cli | autohide
tray_companion = false           ; show tray icon alongside overlay/autohide
```

- [ ] **Step 2: Commit**

```
git add config.ini.example
git commit -m "docs: document tray_companion key in config.ini.example"
```

---

## Task 18: Manual smoke test (Windows)

This task is a checklist, not code. Run after Tasks 1–17 are merged.

- [ ] **Set up:** copy `config.ini.example` → `config.ini`, fill cookies/org_id, set `mode = overlay` and `tray_companion = true`.

- [ ] **Test A — Both visible at start:** `python claude_monitor.py`. Both the overlay window and the tray icon appear. Tray tooltip shows usage. Overlay updates each poll.

- [ ] **Test B — Toggle off via overlay menu:** right-click overlay → "Tray companion" item shows `☑`. Click. Tray icon disappears. `config.ini` now has `tray_companion = false`.

- [ ] **Test C — Toggle on via overlay menu:** right-click overlay → click "Tray companion" again (`☐`). Tray reappears. `config.ini` now has `tray_companion = true`.

- [ ] **Test D — Toggle off via tray menu:** right-click tray → "Turn off tray companion". Tray disappears.

- [ ] **Test E — Switch to autohide keeps companion:** with companion on, right-click overlay → Switch mode → Autohide. Autohide docks to bottom edge; tray icon **stays visible**. Hover the peek strip — autohide slides in.

- [ ] **Test F — Switch to CLI removes companion:** with companion on, right-click autohide → Switch mode → CLI. The console takes over; tray icon disappears.

- [ ] **Test G — Restart preserves state:** quit (Ctrl-C in CLI). Edit `config.ini` `mode = overlay`. Re-launch. Both overlay and tray appear (because `tray_companion = true` was persisted).

- [ ] **Test H — Standalone tray ignores companion flag:** edit `config.ini` `mode = tray`, `tray_companion = true`. Launch. Only one tray icon (no second one). Left-click pops the popup as before.

- [ ] **Test I — Companion left-click focuses overlay:** with overlay+tray, drag overlay behind another window. Click tray icon. Overlay comes to front and gets focus.

- [ ] **Test J — Companion left-click force-shows autohide:** with autohide+tray and the panel hidden, click tray icon. Autohide slides in and locks (force-show on). Right-click → uncheck "Force show" to release.

- [ ] **Test K — `--no-save-mode` does not persist runtime toggle:** launch `python claude_monitor.py --no-save-mode --mode overlay`. Toggle companion off via menu. Quit. Check `config.ini` — `tray_companion` still has its previous value.

- [ ] **Test L — Quit from each menu:** verify Quit from overlay's right-click and Quit from tray's menu both shut everything down cleanly (no orphaned tray icon, console returns).

If any step fails, file as a separate fix task before merging the branch.

---

## Out-of-scope reminders

- No 5th named mode (`tray+overlay`).
- No CLI + tray combo.
- No new companion subsystems beyond tray (the `companion_factories` dict supports it but only `"tray"` is wired today).
