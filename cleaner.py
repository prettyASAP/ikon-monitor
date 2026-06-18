import re
import pandas as pd

from keywords import (
    KEYWORDS, KEYWORD_TIER, ALL_KEYWORDS,
    CONTEXT_WORDS, FALSE_POSITIVE_PATTERNS,
    SOURCES_MEDIA, SOURCES_BULVAR, TIER3_MEDIA_CORE,
)

CONTEXT_BONUS_CAP = 15


# ---------------------------------------------------------------------------
# Forrástípus
# ---------------------------------------------------------------------------

def classify_source(forras: str) -> str:
    if forras in SOURCES_MEDIA:
        return "Médiaipari"
    if forras in SOURCES_BULVAR:
        return "Bulvár"
    return "Egyéb"


# ---------------------------------------------------------------------------
# False positive detekció
# ---------------------------------------------------------------------------

def _is_false_positive(keyword: str, text_original: str, text_lower: str) -> bool:
    if keyword.upper().startswith("IKO"):
        return not bool(re.search(r"\bIKO\b", text_original))

    patterns = FALSE_POSITIVE_PATTERNS.get(keyword, [])
    for p in patterns:
        if re.search(p, text_lower, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Pontozás + indoklás
# ---------------------------------------------------------------------------

def score_article(
    matched_keywords: list[str],
    title: str,
    excerpt: str,
    forras: str = "",
) -> tuple[int, str]:
    """Visszaad (score, miért_szöveg) tuple-t."""
    text_original = f"{title} {excerpt}"
    text_lower = text_original.lower()
    score = 0
    reasons = []

    forras_tipus = classify_source(forras)

    for kw in matched_keywords:
        tier = KEYWORD_TIER.get(kw, "tier3_generikus")
        is_fp = _is_false_positive(kw, text_original, text_lower)

        if tier == "tier1_specifikus":
            if is_fp:
                score += 2
                reasons.append(f"{kw} (FP, T1) +2")
            else:
                score += 40
                reasons.append(f"{kw} (T1) +40")

        elif tier == "tier2_kozepes":
            if is_fp:
                score += 2
                reasons.append(f"{kw} (FP, T2) +2")
            else:
                score += 20
                reasons.append(f"{kw} (T2) +20")

        elif tier == "tier3_generikus":
            pts = 5
            if forras_tipus == "Bulvár":
                pts = max(0, pts - 3)
                reasons.append(f"{kw} (T3, bulvár) +{pts}")
            else:
                reasons.append(f"{kw} (T3) +{pts}")
            score += pts

    # Kontextus bónusz
    ctx_bonus = 0
    ctx_hits = []
    for w in CONTEXT_WORDS:
        if w in text_lower:
            ctx_bonus += 2
            ctx_hits.append(w)
    ctx_bonus = min(ctx_bonus, CONTEXT_BONUS_CAP)
    if ctx_hits:
        score += ctx_bonus
        reasons.append(f"kontextus({','.join(ctx_hits[:4])}) +{ctx_bonus}")

    if forras_tipus == "Bulvár":
        reasons.append("forrás=Bulvár")
    elif forras_tipus == "Médiaipari":
        reasons.append("forrás=Médiaipari")

    return min(score, 100), " | ".join(reasons)


# ---------------------------------------------------------------------------
# Kategorizálás: biztonsági hálókkal
# ---------------------------------------------------------------------------

def _categorize_advanced(
    score: int,
    legjobb_tier: str,
    has_tier1_match: bool,
    has_tier2_fp_media: bool,
    has_tier3_media: bool,
) -> str:
    """
    Garantálja, hogy releváns cikkek ne csússzanak automatikusan Zaj-ba.
    Biztonsági hálók:
    - Tier 1 keyword (FP-vel is): Felülvizsgálandó
    - Tier 2 FP + Médiaipari forrás: Felülvizsgálandó
    - Tier 3 + Médiaipari forrás: Felülvizsgálandó
    """
    if score >= 20:
        return "Releváns"

    if has_tier1_match:
        return "Felülvizsgálandó"
    if has_tier2_fp_media:
        return "Felülvizsgálandó"
    if has_tier3_media:
        return "Felülvizsgálandó"

    if score >= 8:
        return "Felülvizsgálandó"
    return "Zaj"


# ---------------------------------------------------------------------------
# Deduplikálás + pontozás
# ---------------------------------------------------------------------------

def deduplicate_and_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "url" not in df.columns:
        return pd.DataFrame(columns=[
            "datum", "ido", "cim", "forras", "forras_tipus", "lead", "url",
            "matching_keywords", "legjobb_tier", "score", "miért", "kategoria",
        ])

    grouped = (
        df.groupby("url")
        .agg(
            datum=("datum", "first"),
            ido=("ido", "first"),
            cim=("cim", "first"),
            forras=("forras", "first"),
            lead=("lead", "first"),
            matching_keywords=("keyword", lambda x: ", ".join(sorted(set(x)))),
            legjobb_tier=("tier", lambda x: _best_tier(x)),
        )
        .reset_index()
    )

    grouped["forras_tipus"] = grouped["forras"].apply(classify_source)

    scores, reasons, categories = [], [], []
    for _, row in grouped.iterrows():
        kw_list = row["matching_keywords"].split(", ")
        sc, reason = score_article(
            kw_list,
            row["cim"] or "",
            row["lead"] or "",
            row["forras"] or "",
        )

        text_orig = f"{row['cim']} {row['lead']}"
        text_low = text_orig.lower()
        is_media = row["forras_tipus"] == "Médiaipari"

        # Biztonsági háló feltételek
        has_tier1_any = any(KEYWORD_TIER.get(kw) == "tier1_specifikus" for kw in kw_list)

        # Csak "médiaipari jellegű" Tier 3 kulcsszavakra aktiválódik a háló
        # (Tier 2 FP-knél nem szükséges escalation: ha az IKO cég szerepel egy
        # médiaipari cikkben, az mindig benne van a título/leadben is)
        has_tier2_fp_media = False

        has_tier3_media = is_media and any(
            KEYWORD_TIER.get(kw) == "tier3_generikus" and kw in TIER3_MEDIA_CORE
            for kw in kw_list
        )

        cat = _categorize_advanced(
            sc, row["legjobb_tier"],
            has_tier1_any, has_tier2_fp_media, has_tier3_media,
        )
        scores.append(sc)
        reasons.append(reason)
        categories.append(cat)

    grouped["score"] = scores
    grouped["miért"] = reasons
    grouped["kategoria"] = categories

    # Rendezés
    grouped["_datum_sort"] = pd.to_datetime(grouped["datum"], format="%Y.%m.%d", errors="coerce")
    grouped = grouped.sort_values(["_datum_sort", "score"], ascending=[False, False])
    grouped = grouped.drop(columns=["_datum_sort"])

    return grouped


def _best_tier(tiers) -> str:
    order = ["tier1_specifikus", "tier2_kozepes", "tier3_generikus", "ismeretlen"]
    for t in order:
        if t in tiers.values:
            return t
    return "ismeretlen"


# ---------------------------------------------------------------------------
# Sheet szétválasztás
# ---------------------------------------------------------------------------

def split_sheets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "Releváns": df[df["kategoria"] == "Releváns"].copy(),
        "Felülvizsgálandó": df[df["kategoria"] == "Felülvizsgálandó"].copy(),
        "Zaj": df[df["kategoria"] == "Zaj"].copy(),
        "Összes találat": df.copy(),
    }


# ---------------------------------------------------------------------------
# Összefoglaló (MINDEN kulcsszó, 0 találatosak is)
# ---------------------------------------------------------------------------

def build_summary(raw_df: pd.DataFrame, scored_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for kw in ALL_KEYWORDS:
        kw_total = int((raw_df["keyword"] == kw).sum()) if not raw_df.empty else 0
        kw_relevant = 0
        if not scored_df.empty and "matching_keywords" in scored_df.columns:
            kw_relevant = int(
                scored_df[
                    scored_df["matching_keywords"].str.contains(re.escape(kw), na=False)
                    & (scored_df["kategoria"] == "Releváns")
                ].shape[0]
            )
        rows.append({
            "kulcsszó": kw,
            "tier": KEYWORD_TIER.get(kw, "?"),
            "összes_találat": kw_total,
            "releváns_találat": kw_relevant,
            "zaj_%": round(100 * (1 - kw_relevant / kw_total), 1) if kw_total else "-",
        })

    return pd.DataFrame(rows)
