# Tray Companion (Overlay + Tray combo) Design

**Date:** 2026-05-15
**Status:** Draft (pending user approval)
**Project:** claude_monitor
**Supersedes:** none — extends `2026-05-14-multi-mode-display-design.md`

## Problem

The current architecture (`mode_manager.py:22-23`) holds exactly one active view at a time. Switching modes tears down one view and constructs the next. Users who want both an at-a-glance tray indicator **and** the detailed overlay must pick one. The user has asked for an `overlay + tray` combination so the tray icon stays visible at all times while the overlay also shows the full breakdown.

## Goals

- Allow the tray icon to be displayed **alongside** the overlay or autohide view as a "companion" subsystem.
- Keep the existing four standalone modes (`overlay`, `tray`, `cli`, `autohide`) and their CLI/menu/config behavior unchanged.
- Toggle the companion at runtime from either the overlay's right-click menu or the tray's menu.
- Persist the toggle to `config.ini` under the same `--no-save-mode` rule that already governs main-mode persistence.
- Reuse the existing `View` interface — no new abstraction.

## Non-Goals

- Other companion subsystems (notification toasts, etc.). The companion slot is generic but only `tray` is wired today.
- `cli + tray` combo. CLI is foreground stdout, tray is GUI; combining them is rejected by the user (see "Mode compatibility" below).
- A fifth named mode (e.g. `tray+overlay`). The user explicitly chose the auxiliary-toggle model over enumerating combinations.

## User-Visible Behavior

### Activation

Two ways to turn the tray companion on:

1. **Config (`config.ini`):** new key `tray_companion = true` under `[ui]`. Honored at startup.
2. **Runtime toggle:** a check item in **both** menus
   - Overlay right-click: `☑ Tray companion` (label key `menu_tray_companion`)
   - Tray menu (when the tray is running as a companion): `Turn off tray companion` (label key `menu_companion_off`)

### Mode compatibility

The companion is only meaningful when the main view is a GUI overlay-style window. The decision is centralized in one function:

```
_should_show_companion(mode, flag) -> bool
    return flag and mode in {"overlay", "autohide"}
```

| Main mode  | `tray_companion=true` effect           |
|------------|----------------------------------------|
| `overlay`  | tray icon shown alongside overlay      |
| `autohide` | tray icon shown alongside autohide     |
| `tray`     | flag ignored (tray is already main)    |
| `cli`      | flag ignored (no GUI possible)         |

Switching the main mode does **not** automatically toggle the flag. Going `overlay → cli` keeps the flag in config but the companion is not started; going back `cli → overlay` re-evaluates and starts it.

### Tray icon behavior in companion mode

| Action          | Standalone tray (mode=tray)        | Companion tray                                        |
|-----------------|------------------------------------|-------------------------------------------------------|
| Left click      | opens 240×170 popup (current)      | calls `manager.request_focus_main_view()`             |
| Right-click menu top entries | Switch mode, Refresh, Tray settings, Quit | Switch mode, Refresh, Tray settings, **Turn off tray companion**, Quit |
| Tooltip / icon  | unchanged                          | unchanged                                             |
| Hidden Tk root  | created (current)                  | **borrowed** from main view (see Architecture)        |

`request_focus_main_view()`:
- main = `overlay` → `root.lift()` + `attributes("-topmost", True)` + `focus_force()`
- main = `autohide` → flip the existing "force show" toggle on (so the docked panel slides into view)

### Persistence

`request_toggle_companion(on)` calls `save_tray_companion(cfg_path, on)` only when `manager.save_mode is True` (mirrors `_do_switch` at `mode_manager.py:107-111`). Under `--no-save-mode`, runtime toggles are session-local.

### Quit

Both menus' Quit items still call `manager.request_quit()`. The manager stops main view and companion view, then returns from `run()`. Pre-existing semantics; no change.

## Architecture

### `ModeManager` extensions

New fields on `ModeManager`:

- `current_companion: Optional[View]` — the active companion view (or `None`)
- `companion_factories: Dict[str, Callable]` — currently `{"tray": lambda mgr: TrayView(mgr, companion=True)}`
- `tray_companion: bool` — current flag, seeded from config
- `save_tray_companion: Optional[Callable[[Path, bool], None]]` — injected from entry point

New methods:

- `_should_show_companion() -> bool` — single source of truth (see formula above)
- `_sync_companion()` — idempotent: starts companion if needed, stops it if not. Called at the end of `start_initial`, `_do_switch`, and `request_toggle_companion`.
- `request_toggle_companion(on: bool)` — public API for views: updates flag, persists if allowed, syncs.
- `request_focus_main_view()` — public API for the companion tray's left-click handler.

`on_poll_data` change:
```python
for v in (self.current_view, self.current_companion):
    if v is None:
        continue
    # existing root.after vs direct-call branching, applied per view
```

`run()` loop is unchanged: only the **main** view drives the loop. The companion (tray) runs its pystray icon on a daemon thread and pumps Tk via the borrowed root, so the run-loop semantics stay identical.

### `TrayView` becomes dual-mode

`TrayView.__init__(self, manager, *, companion: bool = False)`. The single `companion` flag drives:

- Whether to create its own `tk.Tk()` or borrow `manager.current_view.root` (see "Tk root sharing" below).
- Whether the menu includes the "Turn off tray companion" item.
- Whether left-click opens the popup or calls `manager.request_focus_main_view()`.

`run_mainloop()` is **only called by `ModeManager` for the main view**. The companion tray does not provide a mainloop driver; its work runs via the borrowed root's `after()` queue plus the pystray daemon thread.

### Tk root sharing

The companion tray must not create a competing `tk.Tk()` (Tkinter supports multiple roots but synchronization is fragile, especially during teardown). Pattern:

1. `_sync_companion()` only constructs the companion **after** `current_view.start()` has run, so `current_view.root` is available.
2. Companion `TrayView.start()` reads `manager.current_view.root` (a `tk.Tk`) and uses it for `Toplevel`/messagebox parents and the cross-thread `after()` queue.
3. On a main-view switch (`_do_switch`), the companion is **stopped first**, then the new main view is started, then `_sync_companion()` re-creates the companion bound to the new root. This avoids dangling references to the destroyed old root.

This gives correctness over micro-optimization. Tray briefly disappears during a main-mode switch, but the switch itself already takes a beat.

### `OverlayView` menu addition

Add to `_show_menu` (`overlay.py:186-199`), between Refresh and Quit, with a check mark reflecting `manager.tray_companion`:

```python
menu.add_checkbutton(
    label=T("menu_tray_companion"),
    onvalue=True, offvalue=False,
    variable=tk.BooleanVar(value=self.manager.tray_companion),
    command=lambda: self.manager.request_toggle_companion(not self.manager.tray_companion),
)
```

(Implementation may use a plain command + Unicode `☑/☐` glyph if `add_checkbutton` proves awkward with the dark theme — both are acceptable.)

### `Config` and `i18n`

`config.py`:
- New field `Config.tray_companion: bool` (default `False`).
- New helper `save_tray_companion(cfg_path: Path, value: bool)` mirroring the line-based patcher in `save_mode` (`config.py:47-101`). Same section: `[ui]`. Refactor opportunity: factor the shared key-rewriter out of `save_mode` so both helpers reuse it (`_set_ini_key(path, section, key, value)`).

`i18n.py` (TRANSLATIONS dict):
- `menu_tray_companion`: `"트레이 함께 표시"` / `"Show tray icon"`
- `menu_companion_off`: `"트레이 컴패니언 끄기"` / `"Turn off tray companion"`

### Entry point (`claude_monitor.py`)

After the existing `Config.load`:
```python
mgr = ModeManager(
    cfg_path=CFG_PATH,
    view_factories={...},                         # unchanged
    companion_factories={"tray": lambda m: TrayView(m, companion=True)},
    poller=None,
    save_mode=not args.no_save_mode,
    save_tray_companion=save_tray_companion,
    initial_companion_flag=cfg.tray_companion,
)
```

## Lifecycle & Data Flow

**Startup:**
1. Load config (mode + tray_companion flag).
2. `mgr.start_initial(start_mode)` — constructs/starts main view.
3. `mgr._sync_companion()` — if compatible, constructs and starts companion tray.
4. Poller starts. Both views receive `on_update` via fan-out.

**Mode switch (`request_switch(target)`):**
1. `_pending_switch = target`; `current_view.stop()` → run loop unwinds.
2. `_do_switch(target)`:
   - Stop companion first (releases borrowed root reference).
   - Stop outgoing main view.
   - Construct + start new main view.
   - `_sync_companion()` (re-creates companion if compatible).
3. Run loop re-enters with new view's `run_mainloop`.

**Toggle (`request_toggle_companion(on)`):**
1. `tray_companion = on`.
2. If `save_mode and save_tray_companion`: persist.
3. `_sync_companion()`.

**Quit:**
1. `request_quit()` → `_quit_requested = True`, stop main view, run loop exits.
2. Cleanup also stops `current_companion` if set.

## Edge Cases

- **Standalone tray + flag=true:** `_should_show_companion` returns False → no extra tray. The standalone tray IS the tray.
- **Concurrent left-click + main view destroyed:** `request_focus_main_view` checks `manager.current_view is not None` and `getattr(view, "root", None) is not None` before calling.
- **`_sync_companion` race during switch:** companion is always stopped *before* the main view is replaced. Re-creation happens after the new main view's `start()` has returned, so `current_view.root` is valid.
- **`Config` doesn't have `[ui]` section:** `Config.load` should default `tray_companion` to `False`. `save_tray_companion` creates the section if missing (same pattern as `save_mode`).
- **Quit from companion tray menu:** `request_quit()` stops the main view; the run loop exits; cleanup in `run()` then stops the companion.
- **`autohide` companion left-click:** flips force-show on. Turning it off again is via autohide's own existing UI — companion left-click is a one-way "bring it forward" gesture.

## Testing

**Unit:**

- `tests/test_mode_manager.py` (extend):
  - `_should_show_companion` truth table for all (mode, flag) pairs.
  - `start_initial` constructs companion when applicable; doesn't when not.
  - `_do_switch overlay → autohide` keeps companion alive (with new root).
  - `_do_switch overlay → cli` stops companion.
  - `request_toggle_companion(True/False)` syncs correctly.
  - `--no-save-mode` path: toggle does NOT call `save_tray_companion`.

- `tests/test_config.py` (extend):
  - Round-trip `tray_companion` true/false through `Config.load` + `save_tray_companion`.
  - Default is False when key missing.

**Manual integration (Windows):**

1. Launch with `mode=overlay, tray_companion=true` → both visible.
2. Right-click overlay → uncheck "Tray companion" → tray disappears.
3. Re-check → tray reappears.
4. Right-click overlay → Switch mode → autohide. Tray stays, now bound to autohide root.
5. Switch mode → cli. Tray disappears, console takes over.
6. Quit cli, relaunch → companion restored per saved flag.
7. With `mode=tray`, companion flag is ignored; left-click pops the popup as today.

## Open questions

None — all decisions resolved during brainstorming:

- Companion model: auxiliary toggle (not 5th mode).
- Activation: config + runtime toggle.
- CLI compatibility: excluded.
- Toggle location: both menus.
- Persistence: follows `--no-save-mode`.
- Tray click in companion mode: focus the main view.
