"""Sztori-összevonás és a riport PDF tartalma."""
from __future__ import annotations

from unittest.mock import patch

from ikon.sztori import story_keys
from tests.conftest import insert_article, insert_run


def _a(i, title, score=10, excerpt=""):
    return {"article_id": f"a{i}", "title": title, "excerpt": excerpt, "score": score}


def test_same_story_grouped_different_kept_apart():
    arts = [
        _a(1, "Kiderült, mennyit fizetett a Playboy a 2000-es években magyar celebeknek", 20),
        _a(2, "Kitálalt a magyar Playboy volt főszerkesztője: ennyiért vállalták a celebek"),
        _a(3, "Kitálalt a Playboy, ennyit fizettek a modelljeiknek egy-egy fotózásért"),
        _a(4, "Liptai Claudia elárulta, milyen anyósnak tartja magát"),
        _a(5, "Liptai Claudia überdögös ruhába bújt a premierre"),
        _a(6, "Egy három hete alapított cég vette meg Mészáros Lőrinc milliárdos reklámbirodalmát"),
        _a(7, "Egy három hete alapított cég vette meg Mészáros Lőrinc milliárdos reklámbirodalmát"),
    ]
    k = story_keys(arts)
    assert k["a2"] == k["a3"]
    assert k["a4"] != k["a5"]
    assert k["a6"] == k["a7"]
    assert len({k["a2"], k["a4"], k["a6"]}) == 3


def test_no_chaining_through_bridge_article():
    # A és C csak a középső B-n keresztül hasonlít: nem kerülhetnek egy sztoriba B nélkül
    arts = [
        _a(1, "Marsi Anikó visszatér a képernyőre új műsorral", 30),
        _a(2, "Megrázó vallomást tett Köböl Anita kormányszóvivő", 25),
        _a(3, "Rubint Réka megrázó vallomást tett a Marsi Anikó műsorában", 20),
    ]
    k = story_keys(arts)
    assert k["a1"] != k["a2"]


def test_stories_endpoint(api_client, db_conn):
    insert_run(db_conn, "RUNS1")
    insert_article(db_conn, run_id="RUNS1", article_id="p1", url="https://x.hu/1",
                   title="Kitálalt a magyar Playboy volt főszerkesztője a celebek fizetéséről", score=30)
    insert_article(db_conn, run_id="RUNS1", article_id="p2", url="https://y.hu/2",
                   title="A magyar Playboy volt főszerkesztője kitálalt: ennyit fizettek a celebeknek",
                   score=20, category="felülvizsgálandó")
    r = api_client.get("/api/v1/runs/RUNS1/stories")
    assert r.status_code == 200
    st = r.json()["stories"]
    assert st["p1"] == st["p2"] == "p1"
    assert api_client.get("/api/v1/runs/NINCS/stories").status_code == 404


def test_pdf_includes_undecided_review_and_groups(db_conn):
    from ikon.api.pdf_report import generate_run_pdf
    insert_run(db_conn, "RUNP1")
    insert_article(db_conn, run_id="RUNP1", article_id="r1", url="https://x.hu/r1",
                   title="Biztos hír a Life TV új műsoráról", excerpt="Vacsorakirály évadnyitó", score=30)
    insert_article(db_conn, run_id="RUNP1", article_id="v1", url="https://x.hu/v1",
                   title="Bizonytalan hír Ozone TV nézettségről", excerpt="Egyenlítő adás közönségarány",
                   score=12, category="felülvizsgálandó")
    insert_article(db_conn, run_id="RUNP1", article_id="v2", url="https://x.hu/v2",
                   title="Kivett bizonytalan hír valamiről", excerpt="Időjárás jelentés hétvégére",
                   score=11, category="felülvizsgálandó")
    db_conn.execute("INSERT INTO feedback (url, decision, reviewed_at)"
                    " VALUES ('https://x.hu/v2', 'nem_releváns', datetime('now'))")
    db_conn.commit()
    captured = {}
    with patch("ikon.api.pdf_report._build_pdf", side_effect=lambda run, arts: captured.setdefault("a", arts) and b"%PDF"):
        generate_run_pdf(db_conn, "RUNP1")
    ids = [a["article_id"] for a in captured["a"]]
    assert ids == ["r1", "v1"]


def test_html_not_cached():
    # A felület HTML-je ne kerüljön gyorsítótárba (új verzió után a régi felület ne maradjon)
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.testclient import TestClient
    from starlette.routing import Route

    from ikon.api.app import create_app

    app = create_app()
    app.router.routes.insert(0, Route("/__html", lambda r: HTMLResponse("<p>x</p>")))
    app.router.routes.insert(0, Route("/__json", lambda r: JSONResponse({"ok": True})))
    c = TestClient(app)
    assert c.get("/__html").headers.get("cache-control") == "no-cache"
    assert "cache-control" not in c.get("/__json").headers
