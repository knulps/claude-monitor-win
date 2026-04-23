"""
Claude Usage Floating Overlay
- Always-on-top translucent window
- Drag to reposition
- Right-click menu: refresh / quit
- Auto-refreshes every 60s; countdown ticks every 10s
"""

import configparser
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

try:
    from curl_cffi import requests
    IMPERSONATE = "chrome124"
except ImportError:
    import requests
    IMPERSONATE = None

# ── Config (loaded from config.ini) ──────────────────────────
_cfg = configparser.ConfigParser()
_cfg_path = Path(__file__).parent / "config.ini"
_cfg.read(_cfg_path, encoding="utf-8")

COOKIES       = _cfg.get("claude", "cookies",       fallback="")
ORG_ID        = _cfg.get("claude", "org_id",        fallback="")
POLL_INTERVAL = _cfg.getint("claude", "poll_interval", fallback=60)
LANG          = _cfg.get("ui", "language", fallback="en").lower()
# ──────────────────────────────────────────────────────────────

USAGE_URL = f"https://claude.ai/api/organizations/{ORG_ID}/usage"


# ── i18n ─────────────────────────────────────────────────────
TRANSLATIONS = {
    "en": {
        "session_5h":      "5h session",
        "label_7d":        "7d",
        "reset":           "Reset",
        "reset_7d":        "7d Reset",
        "menu_refresh":    "Refresh now",
        "menu_quit":       "Quit",
        "resetting_soon":  "Resetting soon",
    },
    "ko": {
        "session_5h":      "5h 세션",
        "label_7d":        "7일",
        "reset":           "리셋",
        "reset_7d":        "7일 리셋",
        "menu_refresh":    "지금 새로고침",
        "menu_quit":       "종료",
        "resetting_soon":  "곧 리셋",
    },
}

if LANG not in TRANSLATIONS:
    LANG = "en"


def T(key):
    return TRANSLATIONS[LANG].get(key, key)


# ── Utils ────────────────────────────────────────────────────
def pct_color(pct):
    if pct is None:
        return "#636366"
    if pct < 60:
        return "#30D158"   # green
    if pct < 85:
        return "#FFD60A"   # yellow
    return "#FF453A"       # red


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


# ── Main window ──────────────────────────────────────────────
class ClaudeOverlay:
    W, H = 230, 178   # window size

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)      # no title bar
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#1C1C1E")
        self.root.resizable(False, False)

        # Bottom-right placement (above the taskbar)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.H - 56}")

        self._build_ui()
        self._bind_drag()
        self._bind_menu()

        self._reset_at    = None
        self._reset_7d_at = None
        self._stop        = threading.Event()
        self.data      = {}

        threading.Thread(target=self._poll_loop, daemon=True).start()
        self._tick()

    # ── UI build ─────────────────────────────────────────────
    def _build_ui(self):
        BG   = "#1C1C1E"
        DIM  = "#AEAEB2"
        SEP  = "#2C2C2E"

        # ── Header ──
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(hdr, text="Claude", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self.lbl_updated = tk.Label(hdr, text="", bg=BG, fg=DIM,
                                    font=("Segoe UI", 8))
        self.lbl_updated.pack(side="right")

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        # ── 5h session (main number) ──
        row5 = tk.Frame(self.root, bg=BG)
        row5.pack(fill="x", padx=10, pady=(6, 0))

        tk.Label(row5, text=T("session_5h"), bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left", anchor="s", pady=(0, 4))
        self.lbl_5h_reset = tk.Label(row5, text="", bg=BG, fg=DIM,
                                     font=("Segoe UI", 8))
        self.lbl_5h_reset.pack(side="right", anchor="s", pady=(0, 4))

        self.lbl_5h = tk.Label(self.root, text="—", bg=BG, fg="#30D158",
                               font=("Segoe UI", 32, "bold"))
        self.lbl_5h.pack(anchor="w", padx=10)

        # Progress bar
        outer = tk.Frame(self.root, bg="#3A3A3C", height=5)
        outer.pack(fill="x", padx=10, pady=(0, 6))
        outer.pack_propagate(False)
        self.bar = tk.Frame(outer, bg="#30D158", height=5)
        self.bar.place(x=0, y=0, relheight=1, relwidth=0)

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        # ── Bottom row: 7-day / Sonnet ──
        row7 = tk.Frame(self.root, bg=BG)
        row7.pack(fill="x", padx=10, pady=(5, 2))
        self.lbl_7d     = tk.Label(row7, text=f"{T('label_7d')}  —%", bg=BG, fg="#EBEBF5",
                                   font=("Segoe UI", 10))
        self.lbl_7d.pack(side="left")
        self.lbl_sonnet = tk.Label(row7, text="Sonnet  —%", bg=BG, fg="#EBEBF5",
                                   font=("Segoe UI", 10))
        self.lbl_sonnet.pack(side="right")

        # 7-day reset
        self.lbl_7d_reset = tk.Label(self.root, text="", bg=BG, fg=DIM,
                                     font=("Segoe UI", 8), anchor="w")
        self.lbl_7d_reset.pack(fill="x", padx=10, pady=(0, 2))

        # Extra
        self.lbl_extra = tk.Label(self.root, text="Extra: —", bg=BG, fg=DIM,
                                  font=("Segoe UI", 8), anchor="w")
        self.lbl_extra.pack(fill="x", padx=10, pady=(0, 6))

    # ── Data → UI ────────────────────────────────────────────
    def _refresh_ui(self):
        d  = self.data
        fh = d.get("five_hour")    or {}
        sd = d.get("seven_day")    or {}
        sn = d.get("seven_day_sonnet") or {}
        ex = d.get("extra_usage")  or {}

        # 5h
        pct5 = fh.get("utilization")
        c5   = pct_color(pct5)
        self.lbl_5h.config(
            text=f"{pct5:.0f}%" if pct5 is not None else "—",
            fg=c5,
        )
        self.bar.config(bg=c5)
        self.bar.place(relwidth=(pct5 or 0) / 100)

        # Reset countdown
        self._reset_at = fh.get("resets_at")
        self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(self._reset_at)}")

        # 7-day
        pct7 = sd.get("utilization")
        self.lbl_7d.config(
            text=f"{T('label_7d')}  {pct7:.0f}%" if pct7 is not None else f"{T('label_7d')}  —%",
            fg=pct_color(pct7),
        )
        self._reset_7d_at = sd.get("resets_at")
        self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(self._reset_7d_at)}")

        # Sonnet
        pctsn = sn.get("utilization")
        self.lbl_sonnet.config(
            text=f"Sonnet  {pctsn:.0f}%" if pctsn is not None else "Sonnet  —",
            fg=pct_color(pctsn),
        )

        # Extra
        used  = ex.get("used_credits", 0)
        limit = ex.get("monthly_limit", 0)
        pctex = ex.get("utilization", 0)
        self.lbl_extra.config(
            text=f"Extra: {used:.0f}/{limit} ({pctex:.1f}%)"
        )

        # Update time
        now = datetime.now().strftime("%H:%M")
        self.lbl_updated.config(text=now)

    # ── Countdown + topmost re-apply (every 10s) ─────────────
    def _tick(self):
        # On Windows, fullscreen apps / UAC / sleep-wake can clear topmost.
        # An overrideredirect window has no taskbar presence, so the user
        # has no way to bring it back. Periodically re-toggle to enforce it.
        self.root.attributes("-topmost", False)
        self.root.attributes("-topmost", True)
        self.root.lift()

        if self._reset_at:
            self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(self._reset_at)}")
        if self._reset_7d_at:
            self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(self._reset_7d_at)}")
        self.root.after(10_000, self._tick)

    # ── API polling ──────────────────────────────────────────
    def _fetch(self):
        try:
            kwargs = dict(
                headers={
                    "Cookie": COOKIES,
                    "Accept": "application/json",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                    "Referer": "https://claude.ai/settings/usage",
                    "Origin": "https://claude.ai",
                },
                timeout=10,
            )
            if IMPERSONATE:
                kwargs["impersonate"] = IMPERSONATE
            r = requests.get(USAGE_URL, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[fetch error] {e}")
            return None

    def _poll_loop(self):
        while not self._stop.is_set():
            data = self._fetch()
            if data:
                # /usage endpoint returns either {"five_hour": ...} or {"usage": {...}}
                self.data = data.get("usage", data)
                self.root.after(0, self._refresh_ui)
            self._stop.wait(POLL_INTERVAL)

    # ── Drag ─────────────────────────────────────────────────
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

    # ── Right-click menu ─────────────────────────────────────
    def _bind_menu(self):
        self.root.bind("<Button-3>", self._show_menu)

    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        menu.add_command(label=T("menu_refresh"), command=self._manual_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self._quit)
        menu.post(e.x_root, e.y_root)

    def _manual_refresh(self):
        def _do():
            data = self._fetch()
            if data:
                self.data = data.get("usage", data)
                self.root.after(0, self._refresh_ui)
        threading.Thread(target=_do, daemon=True).start()

    def _quit(self):
        self._stop.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    if not COOKIES:
        print("Set 'cookies' under [claude] in config.ini")
        sys.exit(1)
    if not ORG_ID:
        print("Set 'org_id' under [claude] in config.ini")
        sys.exit(1)
    ClaudeOverlay().run()
