"""Self-check for the start/expiry date-vs-datetime parsing boundary rules.

A bare date must keep the old date-only behavior (start = midnight, expiry =
end of day) while an explicit time overrides it exactly. Run directly:

    python -m custom_components.nimlykoder.test_datetime_boundaries
"""
from datetime import datetime

from .storage import parse_start_datetime, parse_expiry_datetime


def demo() -> None:
    assert parse_start_datetime("2026-09-20") == datetime(2026, 9, 20, 0, 0, 0)
    assert parse_start_datetime("2026-09-20T14:30") == datetime(2026, 9, 20, 14, 30)

    assert parse_expiry_datetime("2026-09-20") == datetime(2026, 9, 20, 23, 59, 59)
    assert parse_expiry_datetime("2026-09-20T10:00") == datetime(2026, 9, 20, 10, 0)

    print("OK")


if __name__ == "__main__":
    demo()
