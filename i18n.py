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
        "resetting_soon":        "곧 리셋",
    },
}

_current_lang = "en"


def set_language(lang):
    """Set the active UI language; falls back to 'en' for unknown codes."""
    global _current_lang
    _current_lang = lang if lang in TRANSLATIONS else "en"


def T(key):
    """Translate a key for the active language; returns the key itself if missing."""
    return TRANSLATIONS[_current_lang].get(key, key)
