import time
import re
from urllib.parse import quote, unquote, urlparse, parse_qs
from datetime import date

import requests
from bs4 import BeautifulSoup

from keywords import ALL_KEYWORDS, KEYWORD_TIER

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "hu-HU,hu;q=0.9",
})


def _fetch(url: str) -> BeautifulSoup:
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _extract_real_url(href: str) -> str:
    """rd.hirkereso.hu redirect URL → tényleges cikk URL."""
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    if "url" in params:
        return params["url"][0]
    return href


def _parse_articles(soup: BeautifulSoup, keyword: str) -> list[dict]:
    articles = []
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
        elif element.name == "li":
            ts = element.find("span", class_="timestamp")
            news_a = element.find("span", class_="news")
            source_span = element.find("span", class_="source")
            lead_span = element.find("span", class_="rowLead")

            if not (ts and news_a):
                continue

            a_tag = news_a.find("a")
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            real_url = _extract_real_url(href)
            source = source_span.get_text(strip=True).strip("()") if source_span else ""
            excerpt = lead_span.get_text(strip=True) if lead_span else ""

            articles.append({
                "datum": current_date,
                "ido": ts.get_text(strip=True),
                "cim": title,
                "forras": source,
                "lead": excerpt,
                "url": real_url,
                "keyword": keyword,
                "tier": KEYWORD_TIER.get(keyword, "ismeretlen"),
            })

    return articles


def _has_next_page(soup: BeautifulSoup) -> bool:
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if "KÖVETKEZŐ" in text.upper() or "»" in text:
            return True
    return False


def scrape_keyword(keyword: str, delay: float = 1.2) -> list[dict]:
    results = []
    page = 1
    while True:
        url = (
            f"https://www.hirkereso.hu/search"
            f"?q={quote(keyword)}&page={page}&timelimit=168"
        )
        try:
            soup = _fetch(url)
        except Exception as e:
            print(f"  [!] Hiba '{keyword}' {page}. oldal: {e}")
            break

        articles = _parse_articles(soup, keyword)
        if not articles:
            break

        results.extend(articles)
        print(f"  '{keyword}' – {page}. oldal: {len(articles)} találat")

        if not _has_next_page(soup):
            break

        page += 1
        time.sleep(delay)

    return results


def scrape_all(delay: float = 1.2) -> list[dict]:
    all_results = []
    total = len(ALL_KEYWORDS)
    for i, kw in enumerate(ALL_KEYWORDS, 1):
        print(f"[{i}/{total}] Keresés: '{kw}'")
        results = scrape_keyword(kw, delay=delay)
        all_results.extend(results)
        time.sleep(delay)
    return all_results


if __name__ == "__main__":
    import pandas as pd
    from pathlib import Path

    Path("output").mkdir(exist_ok=True)
    today = date.today().isoformat()
    raw_path = f"output/raw_{today}.csv"

    data = scrape_all()
    df = pd.DataFrame(data)
    df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"\nNyers találatok mentve: {raw_path} ({len(df)} sor)")
