"""
PDF riport generálás – kurátor export.

Tartalom: releváns cikkek a feedback-kel korrigált kategória szerint.
Fehér hátterű, nyomtatható PDF (A4, reportlab platypus).
"""
from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _register_unicode_font() -> tuple[str, str]:
    """Unicode betűtípust regisztrál a magyar karakterekhez.

    Sorrendben próbálja: matplotlib DejaVu → macOS Arial → Helvetica fallback.
    Visszaad (normal_name, bold_name) tuple-t.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 1) matplotlib DejaVu (legbiztonságosabb cross-platform)
    try:
        import matplotlib
        base = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        reg  = os.path.join(base, "DejaVuSans.ttf")
        bold = os.path.join(base, "DejaVuSans-Bold.ttf")
        if os.path.exists(reg):
            pdfmetrics.registerFont(TTFont("UniSans", reg))
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("UniSans-Bold", bold))
                return "UniSans", "UniSans-Bold"
            return "UniSans", "UniSans"
    except Exception:
        pass

    # 2) Linux rendszerfontek — fonts-liberation csomag (Docker image)
    candidates = [
        ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", "LibSerif",
         "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",    "LibSerif-Bold"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  "LibSans",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",     "LibSans-Bold"),
        # macOS rendszerfontek
        ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", "TNR", "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "TNR-Bold"),
        ("/Library/Fonts/Arial Unicode.ttf",         "SysArialUni", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "SysArialUni-Bold"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "SysArialUni2",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "SysArialUni2-Bold"),
        ("/Library/Fonts/Arial.ttf",                 "SysArial",    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "SysArial-Bold"),
    ]
    for reg_path, name, bold_path, bold_name in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                if os.path.exists(bold_path):
                    try:
                        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
                        return name, bold_name
                    except Exception:
                        pass
                return name, name
            except Exception:
                continue

    # 3) Helvetica fallback
    return "Helvetica", "Helvetica-Bold"


def generate_run_pdf(conn: sqlite3.Connection, run_id: str) -> bytes:
    """Releváns cikkek PDF exportja."""
    run = conn.execute(
        "SELECT run_id, started_at, relevant, review, noise, total_unique,"
        " time_window_hours, COALESCE(keyword_profile, 'iko_ceg') AS keyword_profile"
        " FROM pipeline_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"Run nem található: {run_id}")
    run_dict = dict(run)

    rows = conn.execute(
        """
        SELECT a.title, a.source, a.url, a.score,
               a.published_date_iso, a.excerpt,
               a.matched_keywords, a.score_reason,
               COALESCE(f.decision, '') AS fb_decision,
               COALESCE(f.reviewer_id, '') AS reviewer_id
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

    sources = conn.execute(
        """SELECT a.source, COUNT(*) AS cnt
           FROM articles a
           LEFT JOIN feedback f ON a.url = f.url
           WHERE a.run_id = ?
             AND (
                 (f.decision IS NULL  AND a.category = 'releváns') OR
                 f.decision = 'releváns'
             )
           GROUP BY a.source ORDER BY cnt DESC LIMIT 12""",
        (run_id,),
    ).fetchall()

    articles = [dict(r) for r in rows]
    source_dist = [dict(r) for r in sources]
    profile = run_dict.get("keyword_profile", "iko_ceg")
    return _build_pdf(run_dict, articles, source_dist, profile=profile)


def _date_range_str(run: dict, profile: str = "iko_ceg") -> str:
    try:
        started = datetime.fromisoformat(run["started_at"])
        hours = int(run.get("time_window_hours") or 168)
        if profile == "napi" or hours <= 24:
            # Napi: csak az adott nap, YYYY-MM-DD formátum
            return started.strftime("%Y-%m-%d")
        from_dt = started - timedelta(hours=hours)
        return f"{from_dt.strftime('%Y.%m.%d')} – {started.strftime('%Y.%m.%d')}"
    except Exception:
        return (run.get("started_at") or run["run_id"])[:10]


def _source_chart(source_dist: list[dict], W: float, SANS: str, colors) -> object:
    """Vízszintes sávdiagram a forrás-eloszláshoz reportlab Table+Drawing segítségével."""
    from reportlab.platypus import Table, TableStyle
    from reportlab.graphics.shapes import Drawing, Rect

    if not source_dist:
        return None

    NAME_W = 88.0
    CNT_W  = 24.0
    BAR_W  = W - NAME_W - CNT_W - 8.0  # 8pt padding
    max_cnt = max(s["cnt"] for s in source_dist)
    BAR_CLR = colors.HexColor("#3b82f6")
    TXT_CLR = colors.HexColor("#555555")

    table_rows = []
    for s in source_dist:
        ratio  = s["cnt"] / max_cnt
        filled = max(2.0, BAR_W * ratio)
        d = Drawing(BAR_W, 8)
        d.add(Rect(0, 1.5, filled, 4, fillColor=BAR_CLR, strokeColor=None))
        table_rows.append([s["source"], d, str(s["cnt"])])

    t = Table(table_rows, colWidths=[NAME_W, BAR_W, CNT_W])
    t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), SANS),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TEXTCOLOR",     (0, 0), (0, -1),  TXT_CLR),
        ("TEXTCOLOR",     (2, 0), (2, -1),  TXT_CLR),
        ("ALIGN",         (0, 0), (0, -1),  "LEFT"),
        ("ALIGN",         (2, 0), (2, -1),  "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    return t


def _build_pdf(run: dict, articles: list[dict], source_dist: list[dict] | None = None, profile: str = "iko_ceg") -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        Paragraph, Spacer, HRFlowable, Frame, PageTemplate, KeepTogether,
    )
    from reportlab.platypus.doctemplate import BaseDocTemplate

    buf = io.BytesIO()
    PAGE_W, PAGE_H = A4
    ML, MR, MT, MB = 2.2 * cm, 2.2 * cm, 2.2 * cm, 1.8 * cm
    W = PAGE_W - ML - MR

    SANS, SANS_BOLD = _register_unicode_font()

    base = getSampleStyleSheet()["Normal"]
    base.fontName = SANS

    def ps(name, **kw):
        return ParagraphStyle(name, parent=base, **kw)

    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

    H1_CLR   = colors.HexColor("#111111")
    MUTED    = colors.HexColor("#555555")
    LINK_CLR = colors.HexColor("#0366d6")
    GRAY     = colors.HexColor("#6a737d")
    DIV_CLR  = colors.HexColor("#e1e4e8")
    KW_CLR   = colors.HexColor("#0550ae")

    SZ = 12        # alap betűméret
    LD = SZ * 1.5  # 18pt vezérsor (1.5-ös sorköz)

    title_st = ps("H1",  fontSize=14, leading=21, fontName=SANS_BOLD, textColor=H1_CLR,
                  alignment=TA_CENTER, spaceAfter=4)
    sub_st   = ps("Sub", fontSize=SZ, leading=LD, fontName=SANS,      textColor=MUTED,
                  alignment=TA_CENTER, spaceAfter=14)
    sect_st  = ps("Sec", fontSize=SZ, leading=LD, fontName=SANS_BOLD, textColor=H1_CLR,
                  alignment=TA_LEFT,   spaceBefore=16, spaceAfter=6)
    art_tit  = ps("AT",  fontSize=SZ, leading=LD, fontName=SANS_BOLD, textColor=LINK_CLR,
                  alignment=TA_JUSTIFY, spaceAfter=2)
    art_meta = ps("AM",  fontSize=SZ, leading=LD, fontName=SANS,      textColor=MUTED,
                  alignment=TA_LEFT,   spaceAfter=2)
    art_kw   = ps("AK",  fontSize=SZ, leading=LD, fontName=SANS,      textColor=KW_CLR,
                  alignment=TA_LEFT,   spaceAfter=2)
    art_exc  = ps("AE",  fontSize=SZ, leading=LD, fontName=SANS,      textColor=GRAY,
                  alignment=TA_JUSTIFY, spaceAfter=10)

    # Oldalszámozás nélküli frame
    frame = Frame(ML, MB, W, PAGE_H - MT - MB, id="main")
    tmpl  = PageTemplate(id="std", frames=[frame])
    doc   = BaseDocTemplate(
        buf, pagesize=A4, pageTemplates=[tmpl],
        leftMargin=ML, rightMargin=MR, topMargin=MT, bottomMargin=MB,
    )

    story: list = []

    src_lbl  = ps("SL", fontSize=SZ, leading=LD, fontName=SANS_BOLD, textColor=H1_CLR,
                  alignment=TA_LEFT, spaceBefore=12, spaceAfter=5)

    # ── Fejléc ──────────────────────────────────────────────────────────────
    pdf_title = "Napi sajtóelemzés" if profile == "napi" else "IKO Sajtóelemzés"
    story.append(Paragraph(pdf_title, title_st))
    story.append(Paragraph(_date_range_str(run, profile=profile), sub_st))
    story.append(HRFlowable(width="100%", thickness=0.5, color=DIV_CLR))

    # ── Forrás-eloszlás ─────────────────────────────────────────────────────
    if source_dist:
        story.append(Paragraph("FORRÁSOK", src_lbl))
        chart = _source_chart(source_dist, W, SANS, colors)
        if chart:
            story.append(chart)
        story.append(Spacer(1, 0.25 * cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=DIV_CLR))

    # ── Cikklista ───────────────────────────────────────────────────────────
    story.append(Paragraph(f"Hírek — {len(articles)} db", sect_st))

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _visible_keywords(kws: list, score_reason: str) -> list:
        """FP-ként jelölt kulcsszavakat kiszűri a megjelenítésből.
        A score_reason 'kulcsszó(FP,Tx)+N' formátumot használ."""
        if not score_reason or not kws:
            return kws
        fp_set: set = set()
        for part in score_reason.split(" | "):
            part = part.strip()
            if "(FP," in part:
                fp_set.add(part.split("(")[0].strip())
        return [kw for kw in kws if kw not in fp_set]

    for art in articles:
        raw_title = art.get("title")   or "—"
        source    = art.get("source")  or ""
        url       = art.get("url")     or ""
        date      = (art.get("published_date_iso") or "")[:10]
        excerpt   = art.get("excerpt") or ""
        fb        = art.get("fb_decision") or ""

        raw_kws = art.get("matched_keywords") or "[]"
        score_reason = art.get("score_reason") or ""
        try:
            kws = json.loads(raw_kws) if isinstance(raw_kws, str) else raw_kws
        except (json.JSONDecodeError, TypeError):
            kws = []
        kws = _visible_keywords(kws, score_reason)

        block = [Paragraph(
            f'<link href="{esc(url)}">{esc(raw_title)}</link>',
            art_tit,
        )]
        block.append(Paragraph(f"{esc(source)}  ·  {date}", art_meta))
        if kws:
            kw_str = "  ".join(f"[{esc(k)}]" for k in kws[:6])
            block.append(Paragraph(kw_str, art_kw))
        if excerpt:
            block.append(Paragraph(esc(excerpt), art_exc))
        story.append(KeepTogether(block))
        story.append(HRFlowable(width="100%", thickness=0.3, color=DIV_CLR))

    if not articles:
        story.append(Paragraph("Nincs releváns cikk ebben a futásban.", art_exc))

    doc.build(story)
    return buf.getvalue()
