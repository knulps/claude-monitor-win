# Multi-Mode Display Design

**Date:** 2026-05-14
**Status:** Draft (pending user approval)
**Project:** claude_monitor

## Problem

The current `claude_monitor.py` displays usage as an always-on-top floating overlay (`overrideredirect=True` Tkinter window). Users find the overlay obtrusive because it occupies screen real estate at all times and cannot be unobtrusively tucked away.

The user wants display options that integrate with the Windows taskbar or terminal so the monitor consumes less or no visible screen space when not actively being read.

## Goals

- Provide multiple display modes so users can pick the one that fits their workflow.
- Keep the existing overlay mode unchanged in behavior (it remains the default).
- Let users switch between modes at runtime without restarting, and have the last-selected mode persist across launches.
- Avoid heavy native dependencies. Stay Python-only on Windows 10/11.

## Non-Goals

- macOS or Linux support (out of scope; project is Windows-only today).
- Real Windows taskbar Deskband embedding — Win11 has effectively removed Deskband APIs, and a Python COM implementation would be disproportionate to the user value.
- Win11 Widget Board integration (requires MSIX packaging and WinAppSDK).
- Background notifications/toasts when thresholds are crossed (possible future work; not part of this spec).

## Modes

Four modes are supported. Each mode renders the same underlying usage data; only the presentation differs.

### 1. Overlay (default, current behavior)

- Identical to the current `claude_monitor.py` floating window.
- Right-click menu gains a **"Switch mode ▸"** submenu with entries for Tray, CLI, and Autohide.

### 2. Tray (system notification area)

- A 16×16 system tray icon rendered with `pystray` + `Pillow`.
- **Icon visuals:** filled background in the 5-hour-session status color (green `<60%`, yellow `<85%`, red `85%+`) with the 5-hour utilization percentage drawn in white. Single-digit values are center-aligned; two-digit values use a condensed font; `100%` renders as `!!` on a red background.
- **Hover tooltip** (multi-line, refreshed each poll):
  ```
  Claude Usage  HH:MM
  5h session NN%  · Reset Xh YYm
  7d         NN%  · Reset Xd Yh
  Sonnet      N%
  Extra    N/MM (N.N%)
  ```
- **Left-click:** opens a small popup panel anchored above (or below, depending on taskbar position) the tray icon. The panel is a borderless Tk window (~240×170) showing the same five-line layout as the overlay's main rows. The panel closes when it loses focus (`<FocusOut>`) or when the user clicks outside it.
- **Right-click:** context menu with `Switch mode ▸` (Overlay / CLI / Autohide), `Refresh now`, `Quit`.

### 3. CLI (single-line terminal output)

- No Tkinter window. Output goes directly to stdout.
- Single line, redrawn in place using `\r`, refreshed once per poll. Example:
  ```
  5h 42% 🟢 │ 7d 18% │ Sonnet 5% │ Extra 2/100 │ Reset 2h 14m  [14:23]
  ```
- ANSI color codes for the status indicator and percentages. Windows 10 and 11 conhost/Windows Terminal support ANSI without `colorama`.
- Press `q` + Enter to quit. **Mode switching is one-directional with respect to CLI:** GUI modes can switch *into* CLI (via their right-click "Switch mode" menu), but once in CLI mode the only exit is quitting. To go from CLI back to a GUI mode, the user quits CLI and relaunches with `--mode <gui_mode>` (or with no flag if the saved mode is a GUI mode — note that entering CLI via the menu persists `mode = cli` in `config.ini`, so users will typically need `--mode overlay` on the next launch).
- CLI mode requires a visible console. If launched under `pythonw.exe`, the program exits with a clear error: *"CLI mode requires running with python.exe, not pythonw.exe."* The README's startup instructions are updated to mention this.

### 4. Autohide (edge-docked overlay)

- Subclass of the overlay mode that auto-hides to a screen edge.
- Default edge: right. Only `peek_pixels` (default 3) of the window is visible at rest — the rest sits off-screen via `geometry()`.
- When the mouse enters the visible peek strip, the window slides in over `slide_ms` (default 150ms) using ~10 incremental `geometry()` updates.
- When the mouse leaves the **window's currently visible area** (the fully-expanded rectangle while shown, or just the peek strip while hidden) for `hide_delay_ms` (default 1500ms) without re-entering, the window slides back out.
- Right-click menu is identical to overlay's, plus a **"Force show (lock open)"** toggle that disables auto-hide for the current session — useful when the user can't reach the peek strip on multi-monitor edge cases.

## Architecture

The current single-file design tightly couples API fetch, data parsing, and Tkinter UI. To support four interchangeable views with shared polling, the code is restructured as follows:

```
claude_monitor.py           ← Entry point. Argparse + ModeManager.
config.py                   ← config.ini load/save (mode persistence)
i18n.py                     ← TRANSLATIONS dict + T() helper (moved out of main)
usage_client.py             ← HTTP fetch (_fetch), UsageData parsing
poller.py                   ← Background polling thread + subscriber callback
views/
    base.py                 ← View ABC: start(), stop(), on_update(data)
    overlay.py              ← Current floating window (lightly refactored)
    tray.py                 ← pystray icon + popup panel
    cli.py                  ← Single-line terminal output + 'q' to quit
    autohide.py             ← Subclass of overlay.py with edge-slide behavior
```

### Data flow

```
[Poller thread] ──── poll every POLL_INTERVAL ────► UsageClient.fetch()
                                                          │
                                                          ▼
                                                    UsageData object
                                                          │
                                  ┌───────────────────────┴── cache last value
                                  ▼
                          ModeManager.on_data(data)
                                  │
                                  ▼
                          current_view.on_update(data)   (via tk.after on main thread)
```

- **Poller is owned by `ModeManager`** and survives across mode switches. It never restarts.
- **Last-good data is cached** in `ModeManager`. When a new view starts, it's seeded with the cached value immediately so it doesn't render an empty UI while waiting for the next poll.

### Mode switching flow

```
[Current view] User clicks: right-click → "Switch mode ▸ Tray"
    │
    ▼
ModeManager.switch_to("tray") is called on the main thread
    │
    ├─ 1. current_view.stop()   (CLI's stop() is also called by the 'q' quit path, not from a mode switch)
    │       Overlay/Autohide: root.destroy()
    │       Tray:             pystray icon.stop() + popup destroy
    │       CLI:              set stop event, join output thread, clear line
    │
    ├─ 2. config.save_mode("tray")   (unless --no-save-mode was passed)
    │
    └─ 3. new_view.start()
            Tk-based view: build a fresh tk.Tk() root
            Tray view:     spawn pystray.Icon and start its loop
            CLI view:      start output thread, install SIGINT handler
            All views:     immediately call on_update(cached_data) if non-empty
```

- View transitions are serialized on the main thread via `root.after(0, switch)` or, in CLI mode, via a queue read by the main loop.
- Each Tk-based mode creates and destroys its **own** `tk.Tk()` root. We don't try to reuse a single root across modes — that path causes mainloop reentry issues and isn't worth the complexity.

## Config & CLI Arguments

### config.ini

```ini
[claude]
cookies       = ...
org_id        = ...
poll_interval = 60

[ui]
language = en                ; existing
mode     = overlay           ; new: overlay | tray | cli | autohide

[tray]
popup_position = above       ; above | below

[autohide]
edge          = right        ; right | left | top | bottom
peek_pixels   = 3
slide_ms      = 150
hide_delay_ms = 1500
```

- Mode persistence: when the user switches modes via a context menu, the new value is written back to `[ui] mode`. The write is line-based (find the `mode = …` line in the existing file and replace its value) to preserve comments and ordering. `configparser`'s round-trip rewrite would clobber comments, so we do a targeted text edit instead.
- New sections (`[tray]`, `[autohide]`) are read with `configparser` and have sensible fallbacks via `cfg.get(..., fallback=...)`.

### CLI arguments

```
python claude_monitor.py                      # use config.ini's mode
python claude_monitor.py --mode tray          # override for this session
python claude_monitor.py --mode cli           # terminal mode
python claude_monitor.py --no-save-mode       # don't write back menu-driven mode changes
python claude_monitor.py --help               # argparse standard
```

- `--mode` overrides the `config.ini` value for the initial mode only. If the user then switches modes via the menu, that switch IS saved (unless `--no-save-mode` is also set).
- `argparse` is used for argument parsing — already in the stdlib.

## Edge Cases

| Situation | Handling |
|---|---|
| Switching CLI → GUI mode | Not supported in-process (CLI mode has no menu/UI to trigger a switch). Users quit CLI with `q` and relaunch with the desired `--mode`. The "CLI output thread receives stop event, prints newline, exits" cleanup still applies when quitting. |
| Switching GUI → CLI mode | The Tk root is destroyed. Before starting the CLI view, check `sys.stdout.isatty()` and `os.isatty(1)`. If no console is attached (running under `pythonw.exe`), abort the switch and show a Tk `messagebox` saying CLI mode requires a console; revert to previous mode. |
| Tray popup is open when user opens right-click menu | Right-click menu draws above the popup. If the user picks "Switch mode", both the popup and the tray icon are stopped, then the new view starts. |
| Autohide mode and the user can't reach the peek strip (rare multi-monitor / DPI scaling edge) | "Force show (lock open)" menu item disables auto-hide for the session and keeps the window fully visible at its docked position. |
| Tray icon hidden in Windows notification overflow (`^`) | Standard pystray behavior; not handled in code. README notes: "If the icon isn't visible, open notification area settings → set claude_monitor to 'Always show'." |
| Poller callback arrives mid-switch (between `stop` and `start`) | `ModeManager` always updates its cached data, but only calls `current_view.on_update` if `current_view is not None`. Cached data is replayed when the new view starts. |
| 5-hour utilization ≥ 100% | Tray icon displays `!!` in white on red. Overlay and autohide show `100%` (or higher) in the existing red color. CLI shows the actual percentage in red. |
| Per-language strings for new menu items | `TRANSLATIONS` dict in `i18n.py` gains keys: `menu_switch_mode`, `mode_overlay`, `mode_tray`, `mode_cli`, `mode_autohide`, `menu_force_show`, `cli_quit_hint`, `cli_mode_needs_console`. Both `en` and `ko` entries added. |
| Existing `_tick`-based topmost re-application (overlay) | Retained as-is in overlay mode. Autohide inherits it. Tray and CLI don't need it. |

## Testing Strategy

Polling, parsing, and config save/load are pure logic and get unit tests:

- `test_usage_client.py` — parse `{"usage": {...}}` and flat `{"five_hour": ...}` response shapes. Mock the HTTP layer.
- `test_poller.py` — verify callback fires on successful fetch, doesn't fire on error, respects stop event.
- `test_config.py` — round-trip `[ui] mode` write preserves comments and other keys; reading with missing `mode` key falls back to `overlay`.

Views are validated manually since they're UI:

1. Launch each mode standalone with `--mode <m>` (4 cases).
2. Switch between every pair via the right-click menu: overlay↔tray, overlay↔autohide, tray↔autohide, plus overlay→cli (requires console), cli→overlay (8 transition combos relevant to GUI; CLI transitions require an attached console).
3. Quit and relaunch; confirm last-selected mode is restored from `config.ini`.
4. Pass `--mode tray` when `config.ini` says `overlay`; confirm tray is used. Switch to overlay via menu; quit; relaunch with no flag; confirm overlay is now the persisted default.
5. Pass `--mode tray --no-save-mode`; switch to overlay via menu; quit; relaunch; confirm the saved mode hasn't changed.
6. On a system with multiple monitors / changed DPI, verify autohide's peek strip is on the correct screen edge and the slide animation lands at the right coordinates.
7. Run under `pythonw.exe` and attempt to switch from overlay to CLI; confirm the messagebox appears and the mode doesn't change.

## Dependencies

New packages (added to README install instructions):

- `pystray` — system tray icon
- `Pillow` — image generation for tray icon (`pystray` depends on it anyway)

No other new runtime dependencies. `argparse`, `configparser`, `threading`, `tkinter` are stdlib.

## Open Questions / Deferred

- Whether to expose Sonnet/Extra/7d color thresholds in `config.ini` (currently hardcoded). Out of scope for this spec.
- Whether to add a Windows toast notification when crossing thresholds. Out of scope.
- Whether the tray popup should be draggable to "pin" itself open as a mini-overlay. Out of scope; users wanting a persistent UI should use overlay mode.
