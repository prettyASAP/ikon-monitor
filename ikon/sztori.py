"""Ugyanarról a sztoriról szóló cikkek csoportosítása (több lap ugyanazt a hírt hozza).

Determinisztikus, AI nélkül. Két cikk akkor hasonló, ha elég sok, ritka szótövük közös
(IDF-súlyozott átfedés a rövidebbik cikkhez mérve), a cím alapján vagy a cím és a lead eleje alapján.
Láncolás nincs: a cikkek pontszám szerint sorban egy meglévő sztorihoz csatlakoznak, ha annak
legalább felére közvetlenül hasonlítanak, különben új sztorit nyitnak. Így nem húz össze két különböző hírt
egy harmadik, mindkettőhöz kicsit hasonló cikken keresztül.

A felület és a PDF is ezt használja, így ugyanazt látják. A 2026-11-12/13-i valós adaton hangolva.
"""
from __future__ import annotations

import math
import re
from collections import Counter

# Gyakori, jelentés nélküli szavak (a hírcímekben is sűrűn előfordulnak)
_STOP = {
    "a", "az", "egy", "és", "is", "hogy", "nem", "meg", "már", "még", "volt", "van", "lesz", "lett", "most",
    "csak", "de", "ha", "mert", "mint", "mi", "ki", "mit", "kit", "ez", "ezt", "azt", "ezzel", "arra", "után",
    "elárulta", "videó", "fotók", "fotó", "kiderült", "mutatjuk", "így", "ilyen", "olyan", "minden", "mindent",
    "magyar", "magyarország", "új", "nagy", "első", "sokkal", "aki", "akik", "amit", "amely", "ami",
    "mondta", "szerint", "tett", "kapott", "ennyi", "ennyit", "ezek", "nagyon", "sem", "vagy", "mintha",
}
_WORD = re.compile(r"[a-záéíóöőúüű0-9]{3,}")

# (lead karakterek, küszöb, legalább ennyi közös tő): elég, ha bármelyik szabály teljesül
SZABALYOK = [(0, 0.30, 2), (240, 0.25, 3)]


def _tokens(a: dict, lead: int) -> set[str]:
    text = f"{a.get('title') or ''} {(a.get('excerpt') or '')[:lead]}".lower()
    return {w[:6] for w in _WORD.findall(text) if w not in _STOP}


def story_keys(articles: list[dict]) -> dict[str, str]:
    """article_id → sztori-kulcs (a sztori fő, legjobb pontszámú cikkének azonosítója)."""
    arts = [a for a in articles if a.get("article_id")]
    n = len(arts)
    if not n:
        return {}
    prepared = []
    for lead, th, min_shared in SZABALYOK:
        toks = [_tokens(a, lead) for a in arts]
        df = Counter(t for s in toks for t in s)
        idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        mass = [sum(idf[t] for t in s) or 1.0 for s in toks]
        prepared.append((toks, idf, mass, th, min_shared))

    def similar(i: int, j: int) -> bool:
        for toks, idf, mass, th, min_shared in prepared:
            shared = toks[i] & toks[j]
            if len(shared) >= min_shared and sum(idf[t] for t in shared) / min(mass[i], mass[j]) >= th:
                return True
        return False

    order = sorted(range(n), key=lambda i: (-(arts[i].get("score") or 0), arts[i]["article_id"]))
    clusters: list[list[int]] = []
    for i in order:
        # Akkor csatlakozik, ha a sztori cikkeinek legalább felére hasonlít (a fő cikk is ezek közé számít);
        # több jelölt közül ahhoz, amelyikkel a legnagyobb arányban egyezik.
        best, best_ratio = None, 0.0
        for c in clusters:
            ratio = sum(1 for m in c if similar(i, m)) / len(c)
            if ratio >= 0.5 and ratio > best_ratio:
                best, best_ratio = c, ratio
        if best is None:
            clusters.append([i])
        else:
            best.append(i)
    return {arts[m]["article_id"]: arts[c[0]]["article_id"] for c in clusters for m in c}


def run_story_keys(conn, run_id: str) -> dict[str, str]:
    """Egy futás riportjelölt (releváns és felülvizsgálandó) cikkeinek sztori-kulcsai.

    A visszajelzéstől független halmazon számol, hogy egy kivétel ne rendezze át a többi sztorit.
    """
    rows = conn.execute(
        "SELECT article_id, title, excerpt, score FROM articles"
        " WHERE run_id = ? AND category IN ('releváns', 'felülvizsgálandó')",
        (run_id,),
    ).fetchall()
    return story_keys([dict(r) for r in rows])
