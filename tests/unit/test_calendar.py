"""Unit tests for NSE Trading Calendar and Official Exchange Holidays."""

from __future__ import annotations

from datetime import date

from axiomra.data.calendar import NSETradingCalendar


def test_calendar_trading_days_and_holidays():
    """NSETradingCalendar must flag weekends and official exchange holidays correctly."""
    cal = NSETradingCalendar()

    # Normal trading Monday
    assert cal.is_trading_day(date(2024, 1, 15)) is True

    # Weekend (Saturday & Sunday)
    assert cal.is_trading_day(date(2024, 1, 13)) is False  # Sat
    assert cal.is_trading_day(date(2024, 1, 14)) is False  # Sun

    # Official NSE Holidays (e.g. Republic Day Jan 26, Independence Day Aug 15, Christmas Dec 25)
    assert cal.is_trading_day(date(2024, 1, 26)) is False  # Republic Day
    assert cal.is_trading_day(date(2024, 8, 15)) is False  # Independence Day
    assert cal.is_trading_day(date(2024, 12, 25)) is False  # Christmas


def test_calendar_trading_sessions_between():
    """trading_sessions_between must return trading sessions excluding weekends and holidays."""
    cal = NSETradingCalendar()

    # Range over Republic Day (Jan 22 to Jan 27 2024):
    # Jan 22 (Mon holiday special), Jan 23 (Tue), Jan 24 (Wed), Jan 25 (Thu), Jan 26 (Fri holiday), Jan 27 (Sat)
    # Trading sessions in half-open [Jan 22, Jan 27): Jan 23, Jan 24, Jan 25 (3 sessions)
    sessions = cal.trading_sessions_between(
        start=date(2024, 1, 22),
        end=date(2024, 1, 27),
        include_end=False,
    )
    assert len(sessions) == 3
    assert date(2024, 1, 26) not in sessions
    assert date(2024, 1, 22) not in sessions
