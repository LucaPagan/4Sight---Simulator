from datetime import date, timedelta


def black_friday_date(year: int) -> date:
    first = date(year, 11, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 22)


def calendar_regime(day) -> str:
    current = date.fromisoformat(str(day))
    relative = (current - black_friday_date(current.year)).days
    if relative == 0:
        return "black_friday"
    if relative == 3:
        return "cyber_monday"
    if -7 <= relative <= -1:
        return "black_week"
    if relative in (1, 2):
        return "post_black_friday"
    return "ordinary"


def market_reference_date(day) -> date:
    current = date.fromisoformat(str(day))
    return black_friday_date(2025) + (current - black_friday_date(current.year))
