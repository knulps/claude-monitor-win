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
