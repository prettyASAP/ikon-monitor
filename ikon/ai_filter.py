"""AI-alapú relevancia szűrő – Haiku modellel, batch feldolgozással.

Magyar tévéiparhoz nem kapcsolódó cikkeket szűr ki (külföldi hírek,
politikai tartalom, véletlenszerű kulcsszóegyezések).

Csak relevant+review kategóriára fut; ha ANTHROPIC_API_KEY hiányzik,
kihagyja magát. Kb. $0.10/futás (1200 cikk, 25-ös batch).
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ikon.models import ScoredArticle

logger = logging.getLogger(__name__)

_SYSTEM = """\
Magyar televíziós műsorgyártó cég médiafigyelője szűr. Döntsd el, melyik cikk \
releváns a MAGYAR tévéipar szempontjából.

BELEKERÜL:
- Magyar tévécsatornák (Life TV, Ozone TV, RTL, TV2, Duna TV, stb.) műsorai, hírei
- Magyar médiapiac: nézettség, reklámpiaci hírek, csatornák üzleti hírei
- Magyar tévéiparban ismert személyek (műsorvezetők, tévészereplők) bulvárhírei — \
válás, kapcsolat, botrány, interjú, pályafordulat
- Filmfesztiválok, díjak, ha hazai produkció vagy hazai médium érintett
- Produkciós cégek, gyártás, műsorstruktúra (ha Magyarországon)

NEM KERÜL BELE:
- Külföldi hírek, amelyek nem érintik a magyar médiapiact (Guardian, BBC, stb.)
- Politikai hírek (Magyar Péter, Orbán, pártok, választás) — kivéve ha \
közvetlenül egy médiumot, csatornát érintenek
- Külföldi celebek magánélete (nem hazai tévéhez kötve)
- Külföldi streaming tartalmak (Netflix, HBO, Disney+) önmagukban
- Sport, gazdasági, egészségügyi általános hírek
- Külföldi sportesemények, tudományos hírek"""


def apply_ai_filter(
    articles: list["ScoredArticle"],
    batch_size: int = 25,
) -> list["ScoredArticle"]:
    """AI szűrő alkalmazása relevant+review cikkekre.

    Ha ANTHROPIC_API_KEY nincs beállítva, az összes cikket visszaadja.
    Ha egy batch hibába fut, azt a batch-t megtartja (fail-safe).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("AI szűrő: ANTHROPIC_API_KEY hiányzik → kihagyva")
        return articles

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("AI szűrő: anthropic csomag nincs telepítve → kihagyva")
        return articles

    kept: list[ScoredArticle] = []
    removed = 0

    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        keep_flags = _classify_batch(batch, client)
        for article, keep in zip(batch, keep_flags):
            if keep:
                kept.append(article)
            else:
                removed += 1
                logger.debug("AI kizárta: [%s] %s", article.source, article.title[:70])

    logger.info(
        "AI szűrő: %d cikkből %d maradt (%d kizárva)",
        len(articles), len(kept), removed,
    )
    return kept


def _classify_batch(articles: list["ScoredArticle"], client) -> list[bool]:
    """Visszaad egy bool listát: True = megtartandó."""
    lines: list[str] = []
    for idx, a in enumerate(articles, 1):
        excerpt = (a.excerpt or "")[:120].replace("\n", " ").strip()
        lines.append(f"{idx}. [{a.source}] {a.title}")
        if excerpt:
            lines.append(f"   {excerpt}")

    prompt = (
        "\n".join(lines)
        + "\n\nMely cikkek relevánsak a MAGYAR tévéiparhoz? "
        "Válaszolj CSAK vesszővel elválasztott sorszámokkal (pl. 1,3,7). "
        "Ha egyik sem releváns: -"
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=200,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
    except Exception as exc:
        logger.warning("AI batch hiba (batch %d el): %s — batch megtartva", articles[0].title[:30], exc)
        return [True] * len(articles)

    if text.strip() == "-":
        return [False] * len(articles)

    keep_indices: set[int] = set()
    for part in text.replace(" ", "").split(","):
        # sorszám: pl. "3" vagy "3." ill. tartomány "3-5" nem kell, csak egyedi számok
        part = part.rstrip(".")
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(articles):
                keep_indices.add(idx)

    return [i in keep_indices for i in range(len(articles))]
