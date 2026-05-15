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
ICON_BG = "#000000"  # fully black — maximum contrast against the status-colored digits


def _font(size: int):
    # Regular weight (not Semibold/Black) — thinner digits read better when
    # Windows downsizes the 64px icon to 16/24/32.
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fit_font(draw, text, max_dim):
    """Largest font whose `text` fits within max_dim px (both width and height).

    Lets 1-digit, 2-digit, '!!' and '—' all auto-scale to nearly fill the icon.
    """
    best = _font(8)
    size = 8
    while size < 200:
        candidate = _font(size + 2)
        bbox = draw.textbbox((0, 0), text, font=candidate)
        if bbox[2] - bbox[0] > max_dim or bbox[3] - bbox[1] > max_dim:
            break
        best, size = candidate, size + 2
    return best


def make_icon_image(pct: Optional[float]) -> Image.Image:
    """Dark background with the percentage drawn as large as the icon allows."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), ICON_BG)
    draw = ImageDraw.Draw(img)
    if pct is None:
        text = "—"
    elif pct >= 100:
        text = "!!"
    else:
        text = f"{int(pct)}"
    font = _fit_font(draw, text, ICON_SIZE * 0.96)   # ~no padding
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((ICON_SIZE - tw) / 2 - bbox[0], (ICON_SIZE - th) / 2 - bbox[1]),
              text, fill=pct_color(pct), font=font)
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
                pystray.MenuItem(T("mode_autohide"), lambda: self.manager.request_switch("autohide")),
            )),
            pystray.MenuItem(T("menu_refresh"), lambda: self.manager.request_refresh()),
            pystray.MenuItem(T("menu_tray_settings"), lambda: self._open_tray_settings()),
            pystray.MenuItem(T("menu_quit"),    lambda: self.manager.request_quit()),
            pystray.MenuItem("show", self._on_left_click, default=True, visible=False),
        )

    def _open_tray_settings(self):
        # pystray callback (pystray thread) — marshal the dialog to the Tk main thread.
        self._post(self._show_settings_help)

    def _show_settings_help(self):
        """Explain the Windows setting, then open the Taskbar settings page."""
        try:
            import tkinter.messagebox as mb
            mb.showinfo(T("tray_settings_title"), T("tray_settings_help"))
        except Exception:
            pass
        try:
            import os
            os.startfile("ms-settings:taskbar")
        except Exception as e:
            print(f"[tray] could not open Windows settings: {e}")

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
        # Anchor near the tray icon. "above" = bottom of screen (taskbar at bottom);
        # "below" = top of screen (taskbar at top).
        sw = p.winfo_screenwidth()
        sh = p.winfo_screenheight()
        cfg = getattr(self.manager, "config", None)
        position = cfg.tray_popup_position if cfg else "above"
        if position == "below":
            p.geometry(f"+{sw - 260}+10")
        else:
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
