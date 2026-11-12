"""AI-alapú relevancia szűrő – Haiku modellel, batch feldolgozással.

Magyar tévéiparhoz nem kapcsolódó cikkeket szűr ki (külföldi hírek,
politikai tartalom, véletlenszerű kulcsszóegyezések).

Csak relevant+review kategóriára fut; ha ANTHROPIC_API_KEY hiányzik,
kihagyja magát. Haiku 5.5 ára $0.10/$0.50 per 1M token: futásonként centek.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ikon.models import ScoredArticle

logger = logging.getLogger(__name__)

_SYSTEM = """\
Egy magyar televíziós műsorgyártó cég (IKO Műsorgyártó: Life TV, Ozone TV, \
Media Vivantis) médiafigyelőjének szűrője vagy. A cégnek a MAGYAR médiapiaccal \
kapcsolatos hírek kellenek. Döntsd el cikkenként, hogy ide tartozik-e.

IDE TARTOZIK:
- Magyar tévéműsorok, a saját és a konkurens csatornák műsorai (TV2, RTL, \
Life TV, Ozone TV, Duna, ATV, Hír TV stb.), hírműsorok
- Magyar filmek, sorozatok hírei és utóhírei, bemutatók, díjak
- Bármely magyar tévénél dolgozó vagy korábban dolgozó műsorvezető, szereplő, \
híresség bulvárhíre: válás, szerelmi élet, pletyka, botrány, pályaváltás
- Magyar médiapiac: nézettség, reklámpiac, csatornák, produkciós cégek, \
médiumok üzleti és szervezeti hírei

NEM TARTOZIK IDE:
- Külföldi tartalom és sztár (pl. sikeres Netflix-sorozat, külföldi sztárpár válása)
- Politikai hír (pl. interjút adott Magyar Péter), kivéve ha közvetlenül egy \
médiumot érint (pl. csatorna eladása, médiatörvény, egy szerkesztőség ügye)
- Minden más téma (sport, gazdaság, tudomány, közélet), ha nincs magyar \
média- vagy tévés vonatkozása

Ha a cikk magyar tévés szereplőről, műsorvezetőről, valóságshow-szereplőről \
vagy tévéből, filmből ismert magyar hírességről szól, és bizonytalan vagy, \
tartsd meg: egy kimaradt releváns hír nagyobb hiba, mint egy fölösleges. \
Sportolóra és politikusra ez nem vonatkozik, ha nincs tévés szerepük."""


def apply_ai_filter(
    articles: list["ScoredArticle"],
    batch_size: int = 25,
) -> list["ScoredArticle"]:
    """AI szűrő alkalmazása relevant+review cikkekre.

    - Feedback-jelölt cikkeket (feedback_decision != None) kihagyja a szűrőből.
    - Kizárt cikkek noise kategóriába kerülnek (nem törlődnek), score_reason-be
      '[ai:kizárva]' kerül – utólag ellenőrizhetők.
    - Ha ANTHROPIC_API_KEY hiányzik, az összes cikket változatlanul adja vissza.
    - Ha egy batch hibába fut, azt a batch-t megtartja (fail-safe).
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

    from ikon.models import Category as _Cat

    # Feedback-jelölt cikkeket nem adjuk AI-nak: a felhasználó döntése felülírja a modellét.
    passthrough = [a for a in articles if a.feedback_decision is not None]
    candidates = [a for a in articles if a.feedback_decision is None]

    result: list[ScoredArticle] = list(passthrough)
    removed = 0

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        keep_flags = _classify_batch(batch, client)
        for article, keep in zip(batch, keep_flags):
            if keep:
                result.append(article)
            else:
                removed += 1
                logger.debug("AI kizárta: [%s] %s", article.source, article.title[:70])
                # Noise-ba teszi, nem dobja el — a statisztika és az audit megmarad.
                result.append(article.model_copy(update={
                    "category": _Cat.NOISE,
                    "score_reason": article.score_reason + " [ai:kizárva]",
                }))

    logger.info(
        "AI szűrő: %d cikk (%d feedback-védett), %d kizárva noise-ba",
        len(articles), len(passthrough), removed,
    )
    return result


def _classify_batch(articles: list["ScoredArticle"], client) -> list[bool]:
    """Visszaad egy bool listát: True = megtartandó."""
    lines: list[str] = []
    for idx, a in enumerate(articles, 1):
        excerpt = (a.excerpt or "")[:300].replace("\n", " ").strip()
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
            # A Haiku 5.5 alapból gondolkodik, a gondolkodás is a max_tokens-be számít.
            max_tokens=4000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason in ("refusal", "max_tokens"):
            logger.warning("AI batch: stop_reason=%s — batch megtartva", resp.stop_reason)
            return [True] * len(articles)
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        logger.info("AI batch tokenek: be %d, ki %d", resp.usage.input_tokens, resp.usage.output_tokens)
    except Exception as exc:
        logger.warning("AI batch hiba ('%s'…): %s — batch megtartva", articles[0].title[:30], exc)
        return [True] * len(articles)

    if text.strip() == "-":
        return [False] * len(articles)

    import re as _re
    if not _re.fullmatch(r"[\d,.\s]+", text):
        # Nem a kért formátum → fail-safe: minden cikk megmarad
        logger.warning("AI szűrő: értelmezhetetlen válasz ('%s…') — batch megtartva", text[:60])
        return [True] * len(articles)
    numbers = _re.findall(r"\d+", text)

    keep_indices: set[int] = set()
    for n in numbers:
        idx = int(n) - 1
        if 0 <= idx < len(articles):
            keep_indices.add(idx)

    return [i in keep_indices for i in range(len(articles))]
