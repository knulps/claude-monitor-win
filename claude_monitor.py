"""
Claude Usage Floating Overlay
- 항상 최상위 반투명 창
- 드래그로 위치 이동
- 우클릭 메뉴: 새로고침 / 종료
- 60초마다 자동 갱신, 매분 카운트다운 갱신
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

# ── 설정 (config.ini에서 읽음) ────────────────────────────────
_cfg = configparser.ConfigParser()
_cfg_path = Path(__file__).parent / "config.ini"
_cfg.read(_cfg_path, encoding="utf-8")

COOKIES       = _cfg.get("claude", "cookies",       fallback="")
ORG_ID        = _cfg.get("claude", "org_id",        fallback="")
POLL_INTERVAL = _cfg.getint("claude", "poll_interval", fallback=60)
# ──────────────────────────────────────────────────────────────

USAGE_URL = f"https://claude.ai/api/organizations/{ORG_ID}/usage"


# ── 유틸 ──────────────────────────────────────────────────────
def pct_color(pct):
    if pct is None:
        return "#636366"
    if pct < 60:
        return "#30D158"   # 초록
    if pct < 85:
        return "#FFD60A"   # 노랑
    return "#FF453A"       # 빨강


def time_until(iso_str):
    if not iso_str:
        return "?"
    try:
        reset = datetime.fromisoformat(iso_str)
        now   = datetime.now(timezone.utc)
        secs  = int((reset - now).total_seconds())
        if secs <= 0:
            return "곧 리셋"
        d, r1 = divmod(secs, 86400)
        h, r2 = divmod(r1, 3600)
        m      = r2 // 60
        if d:
            return f"{d}d {h}h"
        return f"{h}h {m:02d}m" if h else f"{m}m"
    except Exception:
        return "?"


# ── 메인 창 ───────────────────────────────────────────────────
class ClaudeOverlay:
    W, H = 230, 178   # 창 크기

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)      # 제목줄 제거
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#1C1C1E")
        self.root.resizable(False, False)

        # 화면 우측 하단 배치 (작업 표시줄 위)
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

    # ── UI 구성 ──────────────────────────────────────────────
    def _build_ui(self):
        BG   = "#1C1C1E"
        DIM  = "#AEAEB2"
        SEP  = "#2C2C2E"

        # ── 헤더 ──
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(hdr, text="Claude", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self.lbl_updated = tk.Label(hdr, text="", bg=BG, fg=DIM,
                                    font=("Segoe UI", 8))
        self.lbl_updated.pack(side="right")

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        # ── 5h 세션 (메인 숫자) ──
        row5 = tk.Frame(self.root, bg=BG)
        row5.pack(fill="x", padx=10, pady=(6, 0))

        tk.Label(row5, text="5h 세션", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left", anchor="s", pady=(0, 4))
        self.lbl_5h_reset = tk.Label(row5, text="", bg=BG, fg=DIM,
                                     font=("Segoe UI", 8))
        self.lbl_5h_reset.pack(side="right", anchor="s", pady=(0, 4))

        self.lbl_5h = tk.Label(self.root, text="—", bg=BG, fg="#30D158",
                               font=("Segoe UI", 32, "bold"))
        self.lbl_5h.pack(anchor="w", padx=10)

        # 프로그레스 바
        outer = tk.Frame(self.root, bg="#3A3A3C", height=5)
        outer.pack(fill="x", padx=10, pady=(0, 6))
        outer.pack_propagate(False)
        self.bar = tk.Frame(outer, bg="#30D158", height=5)
        self.bar.place(x=0, y=0, relheight=1, relwidth=0)

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        # ── 하단 행: 7일 / Sonnet ──
        row7 = tk.Frame(self.root, bg=BG)
        row7.pack(fill="x", padx=10, pady=(5, 2))
        self.lbl_7d     = tk.Label(row7, text="7일  —%",     bg=BG, fg="#EBEBF5",
                                   font=("Segoe UI", 10))
        self.lbl_7d.pack(side="left")
        self.lbl_sonnet = tk.Label(row7, text="Sonnet  —%", bg=BG, fg="#EBEBF5",
                                   font=("Segoe UI", 10))
        self.lbl_sonnet.pack(side="right")

        # 7일 리셋
        self.lbl_7d_reset = tk.Label(self.root, text="", bg=BG, fg=DIM,
                                     font=("Segoe UI", 8), anchor="w")
        self.lbl_7d_reset.pack(fill="x", padx=10, pady=(0, 2))

        # Extra
        self.lbl_extra = tk.Label(self.root, text="Extra: —", bg=BG, fg=DIM,
                                  font=("Segoe UI", 8), anchor="w")
        self.lbl_extra.pack(fill="x", padx=10, pady=(0, 6))

    # ── 데이터 → UI ──────────────────────────────────────────
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

        # 리셋 카운트다운
        self._reset_at = fh.get("resets_at")
        self.lbl_5h_reset.config(text=f"리셋 {time_until(self._reset_at)}")

        # 7일
        pct7 = sd.get("utilization")
        self.lbl_7d.config(
            text=f"7일  {pct7:.0f}%" if pct7 is not None else "7일  —%",
            fg=pct_color(pct7),
        )
        self._reset_7d_at = sd.get("resets_at")
        self.lbl_7d_reset.config(text=f"7일 리셋 {time_until(self._reset_7d_at)}")

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

        # 갱신 시각
        now = datetime.now().strftime("%H:%M")
        self.lbl_updated.config(text=now)

    # ── 카운트다운 + topmost 재적용 (10초마다) ───────────────
    def _tick(self):
        # Windows에서 fullscreen 앱·UAC·절전 복귀 등으로 topmost가 풀리면
        # overrideredirect 창은 taskbar에도 안 떠서 복구 수단이 없다.
        # 주기적으로 토글해 강제로 최상위를 유지한다.
        self.root.attributes("-topmost", False)
        self.root.attributes("-topmost", True)
        self.root.lift()

        if self._reset_at:
            self.lbl_5h_reset.config(text=f"리셋 {time_until(self._reset_at)}")
        if self._reset_7d_at:
            self.lbl_7d_reset.config(text=f"7일 리셋 {time_until(self._reset_7d_at)}")
        self.root.after(10_000, self._tick)

    # ── API 폴링 ─────────────────────────────────────────────
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
                # /usage 엔드포인트가 {"five_hour": ...} 또는 {"usage": {...}} 형태일 수 있음
                self.data = data.get("usage", data)
                self.root.after(0, self._refresh_ui)
            self._stop.wait(POLL_INTERVAL)

    # ── 드래그 ───────────────────────────────────────────────
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

    # ── 우클릭 메뉴 ──────────────────────────────────────────
    def _bind_menu(self):
        self.root.bind("<Button-3>", self._show_menu)

    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        menu.add_command(label="지금 새로고침", command=self._manual_refresh)
        menu.add_separator()
        menu.add_command(label="종료", command=self._quit)
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


# ── 엔트리 ───────────────────────────────────────────────────
if __name__ == "__main__":
    if not COOKIES:
        print("COOKIES를 설정하세요 (스크립트 상단 COOKIES = \"...\")")
        sys.exit(1)
    if not ORG_ID:
        print("ORG_ID를 설정하세요 (스크립트 상단 ORG_ID = \"...\")")
        sys.exit(1)
    ClaudeOverlay().run()
