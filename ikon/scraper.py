"""
hirkereso.hu scraper – típusos, naplózott, rate-limited.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, quote, urlparse

import requests
from bs4 import BeautifulSoup

from ikon.config import ScrapingConfig
from ikon.keywords import ALL_KEYWORDS, KEYWORD_TIER
from ikon.models import RawArticle

logger = logging.getLogger(__name__)

_ENRICH_TIMEOUT = 5   # másodperc / cikk
_ENRICH_WORKERS = 10  # párhuzamos fetch szálak

# og:description tartalmak amik nem cikk-lead-ek, hanem SEO sablonszövegek
_SEO_BLACKLIST = re.compile(
    r"kattints\s+(ide|a\b)"
    r"|feliratkozz"
    r"|hírlevél(re|t)?"
    r"|csak\s+előfizet[oő]knek"
    r"|előfizetős\s+tartalom"
    r"|fizet[oő]s\s+tartalom"
    r"|prémium\s+tartalom",
    re.IGNORECASE,
)


def _fetch_og_description(url: str, session: requests.Session) -> str | None:
    """Kísérli meg a teljes lead kinyerését az eredeti cikk og:description meta tagjából."""
    try:
        resp = session.get(url, timeout=_ENRICH_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for attrs in ({"property": "og:description"}, {"name": "description"}):
            meta = soup.find("meta", attrs=attrs)
            if meta:
                content = (meta.get("content") or "").strip()
                if len(content) > 50 and not _SEO_BLACKLIST.search(content):
                    return content
    except Exception:
        pass
    return None


def _enrich_excerpts(articles: list[RawArticle], session: requests.Session) -> list[RawArticle]:
    """Teljes lead-ek lekérése az eredeti cikk URL-jeiből (og:description).

    Csak akkor frissít, ha az og:description hosszabb a hirkereso.hu által
    visszaadott csonkított excerpt-nél. Egyedi URL-enként egyszer kéri le,
    több kulcsszóra azonos URL esetén is.
    """
    unique_urls = list({a.url for a in articles if a.url})
    if not unique_urls:
        return articles

    logger.info("Excerpt-gazdagítás: %d egyedi URL fetchelése (%d szál)...",
                len(unique_urls), _ENRICH_WORKERS)

    enriched_map: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as pool:
        future_to_url = {pool.submit(_fetch_og_description, url, session): url
                         for url in unique_urls}
        for fut in as_completed(future_to_url):
            url = future_to_url[fut]
            result = fut.result()
            if result:
                enriched_map[url] = result

    _SENTENCE_END = {".", "!", "?", "…", '"', "»", "”"}

    result_list = []
    improved = 0
    for art in articles:
        full = enriched_map.get(art.url, "")
        if full and len(full) > len(art.excerpt):
            art = art.model_copy(update={"excerpt": full})
            improved += 1
        elif art.excerpt and art.excerpt[-1] not in _SENTENCE_END:
            # Fetch nem segített, de a szöveg mondatvég nélkül áll meg → csonkított
            art = art.model_copy(update={"excerpt": art.excerpt + "…"})
        result_list.append(art)

    logger.info("Excerpt-gazdagítás kész: %d/%d cikknél javult a lead", improved, len(unique_urls))
    return result_list


def _build_session(cfg: ScrapingConfig) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": cfg.user_agent,
        "Accept-Language": "hu-HU,hu;q=0.9",
    })
    return s


def _extract_real_url(href: str) -> str:
    """rd.hirkereso.hu redirect URL → tényleges cikk URL."""
    params = parse_qs(urlparse(href).query)
    return params.get("url", [href])[0]


def _parse_page(soup: BeautifulSoup, keyword: str) -> list[RawArticle]:
    articles: list[RawArticle] = []
    current_date = ""

    content_div = soup.find("div", class_="content")
    container = content_div.find("ul") if content_div else None
    if not container:
        return []

    for element in container.children:
        if not hasattr(element, "name"):
            continue

        if element.name == "div" and "daySeparator" in element.get("class", []):
            b = element.find("b")
            if b:
                current_date = b.get_text(strip=True)
            continue

        if element.name != "li":
            continue

        ts_span = element.find("span", class_="timestamp")
        news_span = element.find("span", class_="news")
        source_span = element.find("span", class_="source")
        lead_span = element.find("span", class_="rowLead")

        if not (ts_span and news_span):
            continue

        a_tag = news_span.find("a")
        if not a_tag:
            continue

        articles.append(RawArticle(
            url=_extract_real_url(a_tag.get("href", "")),
            title=a_tag.get_text(strip=True),
            source=source_span.get_text(strip=True).strip("()") if source_span else "",
            published_date=current_date,
            published_time=ts_span.get_text(strip=True),
            excerpt=lead_span.get_text(strip=True) if lead_span else "",
            matched_keyword=keyword,
            keyword_tier=KEYWORD_TIER.get(keyword, "tier3_generikus"),
        ))

    return articles


def _has_next_page(soup: BeautifulSoup) -> bool:
    return any(
        "KÖVETKEZŐ" in a.get_text().upper() or "»" in a.get_text()
        for a in soup.find_all("a", href=True)
    )


def scrape_keyword(
    keyword: str,
    cfg: ScrapingConfig,
    session: requests.Session,
) -> list[RawArticle]:
    """Lekérdezi a megadott kulcsszó összes találatát (paginálással)."""
    results: list[RawArticle] = []
    page = 1

    while True:
        url = (
            f"{cfg.base_url}"
            f"?q={quote(keyword)}&page={page}&timelimit={cfg.time_window_hours}"
        )
        try:
            resp = session.get(url, timeout=cfg.request_timeout_seconds)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            logger.warning("Scraping hiba – '%s' %d. oldal: %s", keyword, page, exc)
            break

        articles = _parse_page(soup, keyword)
        if not articles:
            break

        results.extend(articles)
        logger.debug("  '%s' %d. oldal → %d találat", keyword, page, len(articles))

        if not _has_next_page(soup):
            break

        page += 1
        time.sleep(cfg.request_delay_seconds)

    return results


def scrape_all(
    cfg: ScrapingConfig,
    keywords: "list[str] | None" = None,
) -> list[RawArticle]:
    """Lefuttatja a scraping-et az összes (vagy megadott) kulcsszóra.

    Args:
        cfg:      Scraping konfiguráció.
        keywords: Ha megadott, ezeket a kulcsszavakat scrape-eli.
                  Ha None, a ikon/keywords.py ALL_KEYWORDS listáját használja.
                  A DB-driven keyword management ezen a paraméteren keresztül hat.

    Returns:
        Nyers cikkek listája (duplikátumokkal – a dedup a pipeline-ban történik).
    """
    active_keywords = keywords if keywords is not None else ALL_KEYWORDS
    session = _build_session(cfg)
    all_articles: list[RawArticle] = []
    total = len(active_keywords)

    for i, keyword in enumerate(active_keywords, 1):
        logger.info("[%d/%d] '%s'", i, total, keyword)
        articles = scrape_keyword(keyword, cfg, session)
        all_articles.extend(articles)
        if articles:
            logger.info("  → %d találat", len(articles))
        time.sleep(cfg.request_delay_seconds)

    logger.info("Scraping kész: %d nyers cikk, %d kulcsszó", len(all_articles), total)
    all_articles = _enrich_excerpts(all_articles, session)
    return all_articles
