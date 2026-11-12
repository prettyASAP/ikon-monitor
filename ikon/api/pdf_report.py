"""
PDF riport generálás – az ügyfélnek küldött napi sajtófigyelő.

Tartalom: a riportba kerülő cikkek (feedback-kel korrigált kategória), pontszám szerinti
sorrendben, hírenként a keresőszóval, amelyre bekerült. Csak megjelenés: nincs gépi csoportosítás, összevonás vagy összefoglaló.
A4, egyhasábos, kattintható címek, rövid kivonat, oldalszám.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BUDAPEST = ZoneInfo("Europe/Budapest")
HONAP = ["január", "február", "március", "április", "május", "június", "július",
         "augusztus", "szeptember", "október", "november", "december"]
HONAP_R = ["jan.", "febr.", "márc.", "ápr.", "máj.", "jún.", "júl.", "aug.", "szept.",
           "okt.", "nov.", "dec."]
NAP = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
KIVONAT_MAX = 220


def _register_fonts() -> tuple[str, str]:
    """Talp nélküli Unicode betűtípus (magyar ékezetek). Visszaad (normál, félkövér) nevet."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    try:
        import matplotlib
        base = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        candidates.append((os.path.join(base, "DejaVuSans.ttf"), os.path.join(base, "DejaVuSans-Bold.ttf")))
    except Exception:
        pass
    for reg, bold in candidates:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("IkonSans", reg))
                pdfmetrics.registerFont(TTFont("IkonSans-Bold", bold))
                return "IkonSans", "IkonSans-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def generate_run_pdf(conn: sqlite3.Connection, run_id: str) -> bytes:
    """A riportba kerülő cikkek PDF exportja."""
    run = conn.execute(
        "SELECT run_id, started_at, total_unique, time_window_hours,"
        " COALESCE(keyword_profile, 'iko_ceg') AS keyword_profile"
        " FROM pipeline_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"Run nem található: {run_id}")

    rows = conn.execute(
        """
        SELECT a.title, a.source, a.url, a.score,
               a.published_date_iso, a.published_time, a.excerpt,
               a.matched_keywords, a.score_reason
        FROM articles a
        LEFT JOIN feedback f ON a.url = f.url
        WHERE a.run_id = ?
          AND (
              (f.decision IS NULL  AND a.category = 'releváns') OR
              f.decision = 'releváns'
          )
        ORDER BY a.score DESC
        """,
        (run_id,),
    ).fetchall()

    # Ugyanaz az URL csak egyszer (ez nem tartalmi döntés, ugyanaz a cikk)
    seen: set[str] = set()
    articles = []
    for r in rows:
        a = dict(r)
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        articles.append(a)
    return _build_pdf(dict(run), articles)


def _esc(s: str | None) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _source_name(s: str | None) -> str:
    """„Blikk – aktuális” → „Blikk”: a rovatnév nem forrás."""
    return re.split(r"\s+[–-]\s+", (s or "").strip())[0]


_BYLINE = re.compile(
    r"^[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű.-]+(?: [A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüű.-]+){1,3} "
    r"\d{4}\. ?\d{1,2}\. ?\d{1,2}\.,? ?\w*\.? ?-? ?\d{1,2}:\d{2}\s*"
)


def _excerpt(a: dict, limit: int = KIVONAT_MAX) -> str:
    """Rövid kivonat a forrás leadjéből: cím- és szerzősor nélkül, mondathatáron vágva."""
    t = re.sub(r"\s+", " ", (a.get("excerpt") or "").strip())
    title = (a.get("title") or "").strip()
    if title and t.startswith(title):
        t = t[len(title):].strip()
    t = _BYLINE.sub("", t)
    if len(t) <= limit:
        return t
    cut = t[:limit]
    ends = [m.end() for m in re.finditer(
        r"(?<![\dA-ZÁÉÍÓÖŐÚÜŰ])(?<!stb)(?<!kb)(?<!ill)[.!?…](?=\s+[\"„“A-ZÁÉÍÓÖŐÚÜŰ])", cut)]
    if ends and ends[-1] > limit * 0.45:
        return cut[:ends[-1]]
    return cut[:cut.rfind(" ")].rstrip(",;:") + "…"


_KW_PART = re.compile(r"^(?P<kw>.+?)\((?P<flags>[^)]*)\)")


def _keywords(a: dict) -> list[str]:
    """A keresőszavak, amelyekre a cikk bekerült: konkrétabb tier elöl, a tévesnek (FP) jelöltek nélkül.

    A score_reason formátuma: „Sebestyén Balázs(T2)+20 | műsor(T3,bulvár)+2 | ctx(...)+4”.
    """
    found: list[tuple[int, int, str]] = []
    for i, part in enumerate((a.get("score_reason") or "").split("|")):
        m = _KW_PART.match(part.strip())
        if not m or m.group("kw") == "ctx":
            continue
        flags = [f.strip() for f in m.group("flags").split(",")]
        tier = next((int(f[1:]) for f in flags if re.fullmatch(r"T\d", f)), None)
        if tier is None or "FP" in flags:
            continue
        found.append((tier, i, m.group("kw").strip()))
    if (a.get("score_reason") or "").strip():
        out: list[str] = []
        for _, _, kw in sorted(found):
            if kw not in out:
                out.append(kw)
        return out
    raw = a.get("matched_keywords") or "[]"
    try:
        kws = json.loads(raw) if isinstance(raw, str) else list(raw)
    except (TypeError, ValueError):
        return []
    return [str(k) for k in kws if k]


def _short_date(a: dict) -> str:
    try:
        d = datetime.strptime((a.get("published_date_iso") or "")[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    s = f"{HONAP_R[d.month - 1]} {d.day}."
    if a.get("published_time"):
        s += f" {a['published_time']}"
    return s


def _run_times(run: dict) -> tuple[datetime, datetime]:
    """A futás vége és az időablak eleje budapesti időben (a started_at UTC)."""
    end = datetime.fromisoformat(run["started_at"]).replace(tzinfo=timezone.utc).astimezone(BUDAPEST)
    return end - timedelta(hours=int(run.get("time_window_hours") or 24)), end


def _build_pdf(run: dict, articles: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, KeepTogether,
                                    PageTemplate, Paragraph, Spacer)

    SANS, BOLD = _register_fonts()
    INK, BODY, MUTED, FAINT = (colors.HexColor(c) for c in ("#111827", "#374151", "#6B7280", "#9CA3AF"))
    PAGE_W, PAGE_H = A4
    MX, MTOP, MBOT = 18 * mm, 16 * mm, 18 * mm
    W = PAGE_W - 2 * MX

    start, end = _run_times(run)
    label = "IKO NAPI SAJTÓFIGYELŐ" if run.get("keyword_profile") == "napi" else "IKO SAJTÓFIGYELŐ"
    footer = f"{label.capitalize().replace('Iko', 'IKO')} · {end:%Y. %m. %d.}"

    class NumberedCanvas(rl_canvas.Canvas):
        """Lábléc „oldal / összes” számozással (két menetben)."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages: list[dict] = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont(SANS, 8)
                self.setFillColor(FAINT)
                self.drawString(MX, 10 * mm, footer)
                self.drawRightString(PAGE_W - MX, 10 * mm, f"{self._pageNumber} / {n}")
                super().showPage()
            super().save()

    def st(name: str, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **{"fontName": SANS, **kw})

    s_label = st("label", fontSize=8, leading=10, textColor=MUTED)
    s_date = st("date", fontName=BOLD, fontSize=18, leading=22, textColor=INK)
    s_run = st("run", fontSize=8.5, leading=11, textColor=MUTED)
    s_title = st("title", fontName=BOLD, fontSize=11.5, leading=14.5, textColor=INK)
    s_meta = st("meta", fontSize=8.5, leading=11, textColor=MUTED)
    s_exc = st("exc", fontSize=9.5, leading=13, textColor=BODY)

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=label.capitalize().replace("Iko", "IKO"), author="IKO")
    doc.addPageTemplates([PageTemplate(frames=[Frame(
        MX, MBOT, W, PAGE_H - MTOP - MBOT, id="main",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)])])

    if (end - start) <= timedelta(hours=24):
        heading = f"{end.year}. {HONAP[end.month - 1]} {end.day}., {NAP[end.weekday()]}"
    else:
        heading = f"{start.year}. {HONAP[start.month - 1]} {start.day}. és {HONAP[end.month - 1]} {end.day}. között"
    window = (f"{HONAP_R[start.month - 1]} {start.day}. {start:%H:%M} és "
              f"{HONAP_R[end.month - 1]} {end.day}. {end:%H:%M} között")

    story: list = [
        Paragraph(label, s_label), Spacer(1, 4),
        Paragraph(heading, s_date), Spacer(1, 6),
        Paragraph(f"{len(articles)} cikk, {run.get('total_unique') or 0} átnézett cikkből · {window}", s_run),
        Spacer(1, 8), HRFlowable(width="100%", thickness=0.75, color=INK, spaceAfter=14),
    ]

    for a in articles:
        block = [
            Paragraph(f'<link href="{_esc(a.get("url"))}">{_esc(a.get("title") or "Cím nélkül")}</link>', s_title),
            Spacer(1, 2),
            Paragraph(" · ".join(x for x in (
                _esc(_source_name(a.get("source"))),
                _short_date(a),
                ("Keresőszó: " + _esc(", ".join(_keywords(a)))) if _keywords(a) else "",
            ) if x), s_meta),
        ]
        exc = _excerpt(a)
        if exc:
            block += [Spacer(1, 3), Paragraph(_esc(exc), s_exc)]
        story += [KeepTogether(block), Spacer(1, 12)]

    if not articles:
        story.append(Paragraph("Ebben az időszakban nem volt a riportba illő cikk.", s_exc))

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()
