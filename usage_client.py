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
