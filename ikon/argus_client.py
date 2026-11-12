"""Argus hírkereső kliens – az Observer rendszer REST API-ján keresztül.

Az ARGUS_API_KEY környezeti változóból olvassa a kulcsot.
Visszaad egy list[RawArticle]-t body mezővel feltöltve.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from ikon.keywords import ALL_KEYWORDS, KEYWORD_TIER
from ikon.models import RawArticle

logger = logging.getLogger(__name__)

ARGUS_URL = "https://observer-production-f351.up.railway.app/api/v1/search"
_TZ_BUDAPEST = ZoneInfo("Europe/Budapest")


def _parse_pub_date(raw) -> tuple[str, str]:
    """Visszaad (pub_date YYYY.MM.DD, pub_time HH:MM) párt Budapest időzónában."""
    if not raw or not isinstance(raw, str):
        return "", ""
    try:
        from datetime import timezone as _tz
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        # Naiv (timezone nélküli) időbélyeg → UTC-nek feltételezzük (Observer UTC-ben tárol)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        dt = dt.astimezone(_TZ_BUDAPEST)
        return dt.strftime("%Y.%m.%d"), dt.strftime("%H:%M")
    except ValueError:
        pass
    # Valószínűleg már "YYYY.MM.DD HH:MM" formátum (helyi idő)
    parts = raw.split()
    pub_date = parts[0] if parts else ""
    pub_time = parts[1][:5] if len(parts) > 1 else ""
    return pub_date, pub_time


def scrape_all(
    keywords: "list[str] | None" = None,
    time_window_hours: int = 168,
    api_key: Optional[str] = None,
    from_ts: Optional[int] = None,
) -> list[RawArticle]:
    """Argus API lekérdezés az összes aktív kulcsszóra.

    Args:
        keywords:          Keresendő kulcsszavak. None → ALL_KEYWORDS.
        time_window_hours: Visszatekintési ablak órában.
        api_key:           Argus Bearer token. None → ARGUS_API_KEY env var.
        from_ts:           Pontos ablakkezdet (Unix mp); felülírja a time_window_hours-t.

    Returns:
        list[RawArticle] body mezővel feltöltve.
    """
    if api_key is None:
        api_key = os.environ.get("ARGUS_API_KEY")
    if not api_key:
        raise ValueError("ARGUS_API_KEY nincs beállítva")

    active_keywords = keywords if keywords is not None else ALL_KEYWORDS
    if from_ts is None:
        from_ts = int(time.time()) - time_window_hours * 3600
    headers = {"Authorization": f"Bearer {api_key}"}

    seen: set[tuple[str, str]] = set()  # (url, keyword) – dedup
    articles: list[RawArticle] = []
    total_items = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for keyword in active_keywords:
            tier = KEYWORD_TIER.get(keyword, "tier3_generikus")
            # match=phrase nélkül az Argus a szavakat külön, VAGY-gyal keresi.
            params = {"q": keyword, "match": "phrase", "from": from_ts, "max": 500}
            # Az általános tier3 szavak (műsor, otthon…) a cikktestben szinte mindenhol
            # előfordulnak, ezért csak a címben keressük őket, ahogy a hirkereso.hu tette.
            if tier == "tier3_generikus":
                params["scope"] = "headline"
            try:
                resp = client.get(ARGUS_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                logger.warning("Argus HTTP hiba '%s': %s", keyword, exc.response.status_code)
                continue
            except Exception as exc:
                logger.warning("Argus hiba '%s': %s", keyword, exc)
                continue

            items = data.get("items") or []
            total_items += len(items)
            if len(items) >= 500:
                logger.warning(
                    "Argus '%s': 500-as találati limit elérve, lapozás nincs – korai találatok elveszhetnek",
                    keyword,
                )

            for item in items:
                url = (item.get("url") or "").strip()
                if not url or (url, keyword) in seen:
                    continue
                seen.add((url, keyword))

                src = item.get("source") or {}
                source_name = src.get("name", "") if isinstance(src, dict) else ""

                # A published_at Unix-szám, a published ISO-szöveg: az utóbbit tudjuk értelmezni.
                raw_pub = item.get("published") or ""
                pub_date, pub_time = _parse_pub_date(raw_pub)

                articles.append(RawArticle(
                    url=url,
                    title=(item.get("title") or "").strip(),
                    source=source_name,
                    published_date=pub_date,
                    published_time=pub_time,
                    excerpt=(item.get("description") or "")[:2000],
                    body=(item.get("body") or "")[:50_000],
                    matched_keyword=keyword,
                    keyword_tier=tier,
                ))

            logger.debug("Argus '%s': %d találat", keyword, len(items))

    if active_keywords and not articles:
        logger.warning(
            "Argus 0 cikket adott vissza %d kulcsszóra – ellenőrizd az ARGUS_API_KEY értékét",
            len(active_keywords),
        )
    logger.info(
        "Argus összesen: %d cikk (%d kulcsszóra, %d nyers API találat)",
        len(articles), len(active_keywords), total_items,
    )
    return articles
