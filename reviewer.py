"""
Emberi felülvizsgálati feedback kezelése.

Használat:
    from reviewer import load_feedback, save_feedback, read_decisions_from_excel, apply_feedback_to_scored
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

FEEDBACK_PATH = "output/feedback.json"

DÖNTÉS_RELEVÁNS = "✅ Releváns"
DÖNTÉS_NEM = "❌ Nem releváns"


def load_feedback() -> dict:
    """Betölti a feedback.json-t. Ha nem létezik, üres dict."""
    path = Path(FEEDBACK_PATH)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_feedback(new_decisions: dict):
    """
    Merge-eli az új döntéseket a meglévő feedback.json-ba.
    new_decisions: {url: {"döntés": "releváns"|"nem_releváns", "eredeti_score": int, "megjegyzés": str}}
    """
    existing = load_feedback()
    existing.update(new_decisions)
    Path(FEEDBACK_PATH).parent.mkdir(exist_ok=True)
    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def read_decisions_from_excel(excel_path: str) -> dict:
    """
    Beolvassa a 'Felülvizsgálandó' lap 'Döntés' és 'url' oszlopát.
    Visszatér: {url: {"döntés": ..., "eredeti_score": ..., "megjegyzés": ""}}
    Csak a kitöltött döntéseket (nem üres cellákat) adja vissza.
    """
    try:
        df = pd.read_excel(excel_path, sheet_name="Felülvizsgálandó")
    except Exception as e:
        print(f"[!] Nem sikerült beolvasni a Felülvizsgálandó lapot: {e}")
        return {}

    if "Döntés" not in df.columns or "url" not in df.columns:
        print("[!] Hiányzó 'Döntés' vagy 'url' oszlop a Felülvizsgálandó lapon.")
        return {}

    decisions = {}
    today = date.today().isoformat()
    for _, row in df.iterrows():
        döntés_raw = str(row.get("Döntés", "")).strip()
        url = str(row.get("url", "")).strip()
        if not url or not döntés_raw or döntés_raw in ("nan", ""):
            continue

        if DÖNTÉS_RELEVÁNS in döntés_raw:
            döntés = "releváns"
        elif DÖNTÉS_NEM in döntés_raw:
            döntés = "nem_releváns"
        else:
            continue  # ismeretlen érték → kihagyás

        decisions[url] = {
            "döntés": döntés,
            "átnézve": today,
            "eredeti_score": int(row.get("score", 0)) if pd.notna(row.get("score")) else 0,
            "megjegyzés": str(row.get("Megjegyzés", "")) if pd.notna(row.get("Megjegyzés")) else "",
        }

    return decisions


def apply_feedback_to_scored(scored_df: pd.DataFrame, feedback: dict) -> pd.DataFrame:
    """
    A feedback.json alapján felülírja az automatikus kategóriát.
    - "releváns"     → kategória="Releváns", score=100, feedback_döntés="✅ Jóváhagyva"
    - "nem_releváns" → kategória="Zaj",      score=0,   feedback_döntés="❌ Elutasítva"
    """
    if scored_df.empty or not feedback:
        scored_df["feedback_döntés"] = ""
        return scored_df

    df = scored_df.copy()
    df["feedback_döntés"] = ""

    for idx, row in df.iterrows():
        url = str(row.get("url", ""))
        if url in feedback:
            entry = feedback[url]
            if entry["döntés"] == "releváns":
                df.at[idx, "kategoria"] = "Releváns"
                df.at[idx, "score"] = 100
                df.at[idx, "feedback_döntés"] = "✅ Jóváhagyva"
            elif entry["döntés"] == "nem_releváns":
                df.at[idx, "kategoria"] = "Zaj"
                df.at[idx, "score"] = 0
                df.at[idx, "feedback_döntés"] = "❌ Elutasítva"

    return df


def print_feedback_stats(decisions: dict):
    releváns = sum(1 for v in decisions.values() if v["döntés"] == "releváns")
    nem = sum(1 for v in decisions.values() if v["döntés"] == "nem_releváns")
    print(f"  Mentett döntések: {releváns} releváns + {nem} nem releváns")
    all_fb = load_feedback()
    print(f"  Feedback.json összesen: {len(all_fb)} URL")
