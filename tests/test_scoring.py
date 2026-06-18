"""
Unit tesztek a scoring modulhoz.

Ezek a tesztek a pipeline-tól teljesen független, tiszta függvényeket
tesztelik – futtatásuk nem igényel hálózatot, DB-t vagy fájlrendszert.

    pytest tests/test_scoring.py -v
"""
from __future__ import annotations

import pytest

from ikon.config import ScoringConfig, ScoringThresholds
from ikon.models import Category, SourceType
from ikon.scoring import (
    ScoreResult,
    categorize,
    classify_source,
    is_false_positive,
    score_article,
)


# ---------------------------------------------------------------------------
# is_false_positive
# ---------------------------------------------------------------------------

class TestIsFalsePositive:
    def test_iko_keyword_without_uppercase_iko_is_fp(self):
        # "ikonikus" a szövegben, "IKO" nagybetűsen nem → false positive
        assert is_false_positive("IKO", "Az ikonikus vezető megszólalt", "") is True

    def test_iko_keyword_with_uppercase_iko_is_not_fp(self):
        # "IKO" nagybetűsen megjelenik → valódi találat
        assert is_false_positive("IKO", "Az IKO Műsorgyártó bejelentette...", "") is False

    def test_iko_musorgyarto_tier1_with_iko_in_title(self):
        assert is_false_positive(
            "IKO Műsorgyártó",
            "IKO Műsorgyártó díjat nyert",
            "",
        ) is False

    def test_iko_tier1_without_iko_in_text_is_fp(self):
        # Tier 1 "IKO Műsorgyártó" – de a szövegben nincs "IKO" → FP
        assert is_false_positive(
            "IKO Műsorgyártó",
            "Ikonikus produkciós vállalkozás díjat nyert",
            "",
        ) is True

    def test_dialogue_with_conversation_word_is_fp(self):
        # "párbeszéd" = FP pattern Dialogue-ra
        assert is_false_positive(
            "Dialogue",
            "Átfogó párbeszéd zajlott a felek között",
            "parlamenti párbeszéd",
        ) is True

    def test_dialogue_creative_is_not_fp(self):
        # "dialogue creative" szövegkörnyezetben nem FP
        assert is_false_positive(
            "Dialogue",
            "A Dialogue Creative Agency új kampányt indít",
            "dialogue creative megbízás",
        ) is False

    def test_kovacs_gergely_politician_is_fp(self):
        # MKKP politikus → FP
        assert is_false_positive(
            "Kovács Gergely",
            "Kovács Gergely MKKP képviselő interpellált",
            "kutya párt kovács gergely",
        ) is True

    def test_keyword_without_patterns_is_never_fp(self):
        # "Somodi Hajnalka" – nincs FP pattern, soha nem FP
        assert is_false_positive("Somodi Hajnalka", "Somodi Hajnalka nyilatkozott", "") is False


# ---------------------------------------------------------------------------
# classify_source
# ---------------------------------------------------------------------------

class TestClassifySource:
    def test_media1_is_media(self):
        assert classify_source("Media1") == SourceType.MEDIA

    def test_mediapiac_is_media(self):
        assert classify_source("Médiapiac") == SourceType.MEDIA

    def test_blikk_is_tabloid(self):
        assert classify_source("Blikk") == SourceType.TABLOID

    def test_blikk_with_dot_is_tabloid(self):
        assert classify_source("Blikk.") == SourceType.TABLOID

    def test_unknown_source_is_other(self):
        assert classify_source("Ismeretlen Lap") == SourceType.OTHER

    def test_index_variants(self):
        assert classify_source("Index - kf") == SourceType.MEDIA
        assert classify_source("Index - g") == SourceType.MEDIA


# ---------------------------------------------------------------------------
# score_article
# ---------------------------------------------------------------------------

class TestScoreArticle:
    @pytest.fixture
    def cfg(self) -> ScoringConfig:
        return ScoringConfig(thresholds=ScoringThresholds(relevant=20, review=8))

    def test_tier1_keyword_gives_40_points(self, cfg):
        result = score_article(
            ["IKO Műsorgyártó"],
            "IKO Műsorgyártó díjat nyert",
            "",
            "Media1",
            cfg,
        )
        assert result.score >= 40

    def test_false_positive_tier1_scores_much_less_than_real_match(self, cfg):
        # "IKO Műsorgyártó" de szövegben nincs "IKO" → FP → sokkal kevesebb pont
        real = score_article(
            ["IKO Műsorgyártó"],
            "IKO Műsorgyártó díjat nyert",
            "",
            "Médiapiac",
            cfg,
        )
        fp = score_article(
            ["IKO Műsorgyártó"],
            "Ikonikus produkciós cég díjat nyert",
            "",
            "",  # semleges forrás → nincs kontextus bonus torzítás
            cfg,
        )
        assert fp.score < cfg.tier2_base_score  # közelebb a penalty-hez, mint egy valódi tier2-hez
        assert real.score >= cfg.tier1_base_score

    def test_tier2_keyword_without_fp_gives_20(self, cfg):
        result = score_article(["TV2"], "TV2 rekordnézettséget ért el", "", "Médiapiac", cfg)
        assert result.score >= 20

    def test_tier3_tabloid_source_penalized(self, cfg):
        result_tabloid = score_article(["nézettség"], "Nézettségi adatok", "", "Blikk", cfg)
        result_media = score_article(["nézettség"], "Nézettségi adatok", "", "Médiapiac", cfg)
        assert result_tabloid.score < result_media.score

    def test_context_words_add_bonus(self, cfg):
        without_ctx = score_article(["producer"], "Egy producer nyilatkozott", "", "", cfg)
        with_ctx = score_article(["producer"], "TV2 producer műsor adás sorozat televízi", "", "", cfg)
        assert with_ctx.score > without_ctx.score

    def test_context_bonus_capped(self, cfg):
        # Sok kontextus szó → max cfg.context_bonus_cap
        result = score_article(
            ["nézettség"],
            "tv2 műsor produkci csatorn televízi nézett médiai gyártó reklám adás sorozat iko dialogue indamedia vaszily somodi",
            "",
            "",
            cfg,
        )
        # A kontextus bónusz nem lehet több mint context_bonus_cap
        # A végső score = tier3_base_score + context_bonus_cap
        assert result.score <= cfg.tier3_base_score + cfg.context_bonus_cap

    def test_score_capped_at_100(self, cfg):
        result = score_article(
            ["IKO Műsorgyártó", "IKO Productions", "Somodi Hajnalka", "TV2", "Dialogue"],
            "IKO IKO IKO TV2 Dialogue Somodi Hajnalka",
            "IKO Műsorgyártó IKO Productions tv2 dialogue produkci műsor csatorn",
            "Médiapiac",
            cfg,
        )
        assert result.score <= 100

    def test_score_reason_not_empty_when_keywords_match(self, cfg):
        result = score_article(["TV2"], "TV2 bejelentette", "", "Media1", cfg)
        assert result.reason


# ---------------------------------------------------------------------------
# categorize
# ---------------------------------------------------------------------------

class TestCategorize:
    @pytest.fixture
    def cfg(self) -> ScoringConfig:
        return ScoringConfig(thresholds=ScoringThresholds(relevant=20, review=8))

    def test_high_score_is_relevant(self, cfg):
        cat, _ = categorize(40, SourceType.MEDIA, ["IKO Műsorgyártó"], "IKO", "", cfg)
        assert cat == Category.RELEVANT

    def test_score_at_threshold_is_relevant(self, cfg):
        cat, _ = categorize(20, SourceType.OTHER, ["TV2"], "TV2", "", cfg)
        assert cat == Category.RELEVANT

    def test_medium_score_is_review(self, cfg):
        cat, _ = categorize(15, SourceType.OTHER, ["producer"], "producer", "", cfg)
        assert cat == Category.REVIEW

    def test_low_score_without_safetynet_is_noise(self, cfg):
        cat, _ = categorize(3, SourceType.OTHER, ["producer"], "producer", "", cfg)
        assert cat == Category.NOISE

    def test_tier1_keyword_always_at_least_review(self, cfg):
        # Alacsony pontszám, de valódi (nem FP) Tier 1 kulcsszó → nem mehet Zajba.
        # A cím tartalmazza az "IKO" szót önálló tokenként, tehát is_false_positive = False.
        cat, flags = categorize(
            2, SourceType.OTHER, ["IKO Műsorgyártó"],
            "IKO produkciós cég nyert díjat", "", cfg
        )
        assert cat == Category.REVIEW
        assert flags.has_tier1_keyword is True

    def test_tier3_media_core_with_media_source_is_review(self, cfg):
        cat, flags = categorize(
            5, SourceType.MEDIA, ["nézettség"],
            "Nézettségi adatok a televíziós piacon", "", cfg
        )
        assert cat == Category.REVIEW
        assert flags.has_tier3_media_core is True

    def test_tier3_media_core_with_tabloid_is_noise(self, cfg):
        cat, _ = categorize(
            2, SourceType.TABLOID, ["nézettség"],
            "Nézettségi adatok", "", cfg
        )
        assert cat == Category.NOISE


# ---------------------------------------------------------------------------
# ScoreResult NamedTuple / Dataclass contract
# ---------------------------------------------------------------------------

class TestScoreResult:
    def test_score_result_is_frozen(self):
        result = ScoreResult(score=42, reason="T1+40|ctx+2")
        with pytest.raises((AttributeError, TypeError)):
            result.score = 0  # type: ignore[misc]

    def test_score_result_attributes(self):
        result = ScoreResult(score=10, reason="test")
        assert result.score == 10
        assert result.reason == "test"
