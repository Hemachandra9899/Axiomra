"""NSE Trading Calendar and Official Exchange Holidays (2017–2026)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

# Official NSE Cash Market Exchange Holidays (2017–2026)
NSE_HOLIDAYS: set[date] = {
    # 2017
    date(2017, 1, 26), date(2017, 2, 24), date(2017, 3, 13), date(2017, 4, 4),
    date(2017, 4, 14), date(2017, 5, 1), date(2017, 6, 26), date(2017, 8, 15),
    date(2017, 8, 25), date(2017, 10, 2), date(2017, 10, 19), date(2017, 10, 20),
    date(2017, 11, 4), date(2017, 12, 25),
    # 2018
    date(2018, 1, 26), date(2018, 2, 13), date(2018, 3, 2), date(2018, 3, 29),
    date(2018, 3, 30), date(2018, 4, 30), date(2018, 5, 1), date(2018, 8, 15),
    date(2018, 8, 22), date(2018, 9, 13), date(2018, 9, 20), date(2018, 10, 2),
    date(2018, 10, 18), date(2018, 11, 7), date(2018, 11, 8), date(2018, 11, 23),
    date(2018, 12, 25),
    # 2019
    date(2019, 3, 4), date(2019, 3, 21), date(2019, 4, 17), date(2019, 4, 19),
    date(2019, 4, 29), date(2019, 5, 1), date(2019, 6, 5), date(2019, 8, 12),
    date(2019, 8, 15), date(2019, 9, 2), date(2019, 9, 10), date(2019, 10, 2),
    date(2019, 10, 8), date(2019, 10, 21), date(2019, 10, 28), date(2019, 11, 12),
    date(2019, 12, 25),
    # 2020
    date(2020, 2, 21), date(2020, 3, 10), date(2020, 4, 2), date(2020, 4, 6),
    date(2020, 4, 10), date(2020, 4, 14), date(2020, 5, 1), date(2020, 5, 25),
    date(2020, 10, 2), date(2020, 11, 16), date(2020, 11, 30), date(2020, 12, 25),
    # 2021
    date(2021, 1, 26), date(2021, 3, 11), date(2021, 3, 29), date(2021, 4, 2),
    date(2021, 4, 14), date(2021, 4, 21), date(2021, 5, 13), date(2021, 7, 21),
    date(2021, 8, 19), date(2021, 9, 10), date(2021, 10, 12), date(2021, 10, 15),
    date(2021, 11, 4), date(2021, 11, 5), date(2021, 11, 19),
    # 2022
    date(2022, 1, 26), date(2022, 3, 1), date(2022, 3, 18), date(2022, 4, 14),
    date(2022, 4, 15), date(2022, 5, 3), date(2022, 8, 9), date(2022, 8, 15),
    date(2022, 8, 31), date(2022, 10, 5), date(2022, 10, 24), date(2022, 10, 26),
    date(2022, 11, 8),
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30), date(2023, 4, 4),
    date(2023, 4, 7), date(2023, 4, 14), date(2023, 5, 1), date(2023, 6, 29),
    date(2023, 8, 15), date(2023, 9, 19), date(2023, 10, 2), date(2023, 10, 24),
    date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 22), date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25),
    date(2024, 3, 29), date(2024, 4, 11), date(2024, 4, 17), date(2024, 5, 1),
    date(2024, 5, 20), date(2024, 6, 17), date(2024, 7, 17), date(2024, 8, 15),
    date(2024, 10, 2), date(2024, 11, 1), date(2024, 11, 15), date(2024, 12, 25),
    # 2025
    date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31), date(2025, 4, 10),
    date(2025, 4, 14), date(2025, 4, 18), date(2025, 5, 1), date(2025, 8, 15),
    date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25),
    # 2026
    date(2026, 1, 26), date(2026, 2, 16), date(2026, 3, 3), date(2026, 3, 20),
    date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1), date(2026, 5, 28),
    date(2026, 8, 15), date(2026, 9, 15), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 9), date(2026, 12, 25),
}


class NSETradingCalendar:
    """Official NSE Cash Market Trading Calendar."""

    def __init__(self, holidays: set[date] | None = None) -> None:
        self.holidays = holidays if holidays is not None else NSE_HOLIDAYS

    def is_trading_day(self, dt: date | datetime) -> bool:
        """Return True if dt is a Monday–Friday non-holiday trading session."""
        d = dt.date() if isinstance(dt, datetime) else dt
        return d.weekday() < 5 and d not in self.holidays

    def trading_sessions_between(
        self,
        start: date | datetime,
        end: date | datetime,
        include_end: bool = False,
    ) -> list[date]:
        """Return list of valid trading session dates in interval [start, end) or [start, end]."""
        start_d = start.date() if isinstance(start, datetime) else start
        end_d = end.date() if isinstance(end, datetime) else end

        sessions: list[date] = []
        curr = start_d
        while curr < end_d if not include_end else curr <= end_d:
            if self.is_trading_day(curr):
                sessions.append(curr)
            curr += timedelta(days=1)
        return sessions
