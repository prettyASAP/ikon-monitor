"""A napi gyűjtés időablaka: az előző nap 9:00-tól (budapesti idő), hétfőn a péntek 9:00-tól."""
from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BUDAPEST = ZoneInfo("Europe/Budapest")
KEZDO_ORA = time(9, 0)


def munkanap_kezdet(now: datetime | None = None) -> datetime:
    """Az ablak kezdete UTC-ben. Hétfőn 3 napot lép vissza (péntek), egyébként egyet."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    helyi = now.astimezone(BUDAPEST)
    nap = helyi.date() - timedelta(days=3 if helyi.weekday() == 0 else 1)
    return datetime.combine(nap, KEZDO_ORA, tzinfo=BUDAPEST).astimezone(timezone.utc)


def ablak_orak(kezdet: datetime, now: datetime | None = None) -> int:
    """Egész órában (felfelé kerekítve) azoknak a forrásoknak, amelyek csak órát fogadnak."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(1, math.ceil((now - kezdet).total_seconds() / 3600))
