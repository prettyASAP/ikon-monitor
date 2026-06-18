"""
Embedding-alapú szemantikai hasonlóság — false-negative rescue.

A modell egyszer töltődik be (process-szintű cache), utána csak a batch
inference fut. 200 cikk CPU-n kb. 1-2 másodperc.

Első futáskor letölti a modellt (~470 MB, egyszer, Hugging Face cache-be).
"""
from __future__ import annotations

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_model = None
_ref_embs = None  # referencia vektorok cachelve

# Referencia mondatok: az IKO-releváns tartalom leírása.
# Minél közelebb van egy cikk ezekhez szemantikailag, annál valószínűbb, hogy releváns.
REFERENCE_SENTENCES: List[str] = [
    "IKO Műsorgyártó Magyarország televíziós produkciós cég",
    "Dialogue Creative Agency reklámügynökség médiavásárlás kampány",
    "Indamedia Sales House hirdetési médiapiaci megjelenés",
    "Big Picture Conference médiaipari szakmai esemény",
    "Somodi Hajnalka Vaszily Miklós Kovács Gergely médiaipari vezető",
    "televíziós műsorgyártás broadcast produkció tartalom gyártó cég",
    "branded content natív hirdetés szponzorált tartalom médiaipari",
    "Nielsen közönségmérés televíziós nézettségi adatok kutatás",
    "csatornaindítás műsorstruktúra televíziós reklámpiac médiaipac",
    "Magyar Mozgókép Díj Televíziós Újságírók Díja filmes elismerés",
    "executive producer filmgyártás produkciós vállalat",
    "médiapiac reklámszektor tartalom marketing hirdetési ipar",
]


def _get_model():
    global _model, _ref_embs
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Embedding modell betöltése: %s (első futásnál letöltés ~470 MB)", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        _ref_embs = _model.encode(
            REFERENCE_SENTENCES,
            batch_size=len(REFERENCE_SENTENCES),
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        logger.info("Embedding modell és referencia vektorok kész")
    return _model, _ref_embs


def compute_similarity(texts: List[str]) -> np.ndarray:
    """Visszaadja a referencia mondatokhoz való max. koszinusz-hasonlóságot.

    Args:
        texts: Szövegek listája (pl. ['cím. lead', ...]).

    Returns:
        np.ndarray shape (n,) – minden szöveghez a legmagasabb hasonlóság (0–1).
    """
    if not texts:
        return np.array([])

    model, ref_embs = _get_model()
    text_embs = model.encode(
        texts,
        batch_size=128,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    # Normalizált vektoroknál dot product = koszinusz-hasonlóság
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        sims = text_embs @ ref_embs.T  # (n_texts, n_refs)
    sims = np.nan_to_num(sims, nan=0.0, posinf=0.0, neginf=0.0)
    return sims.max(axis=1)  # (n_texts,) — legjobb referencia per szöveg
