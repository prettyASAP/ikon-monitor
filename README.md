# ikon-monitor

[![tests](https://github.com/prettyASAP/ikon-monitor/actions/workflows/tests.yml/badge.svg)](https://github.com/prettyASAP/ikon-monitor/actions/workflows/tests.yml)

Média-monitoring pipeline és webes felület egy televíziós műsorgyártó cég számára. Naponta, illetve hetente összegyűjti a magyar online sajtó releváns cikkeit, pontozza és három kategóriába sorolja őket (releváns, felülvizsgálandó, zaj), az elemző döntéseit pedig visszacsatolja a pontozásba.

## Hogyan működik

```
scrape  →  deduplikálás  →  pontozás  →  embedding-mentés  →  SQLite  →  Excel / PDF / web
```

1. **Gyűjtés:** a hírkereső aggregátor keresési találatai kulcsszavanként, állítható időablakkal (napi vagy heti futás) és kéréskésleltetéssel.
2. **Pontozás:** három szintű kulcsszórendszer (pontos cég- és személynév, közepes specificitású kifejezés, iparági általános kifejezés). A pontszámot a szint, a téves egyezések szűrése, a médiaipari kontextusszavak és a forrás típusa (pl. bulvár) alakítja. Minden küszöb és súly a `config/settings.yaml`-ban van, a kódban nincs beégetett szám.
3. **Téves negatívok mentése:** a zajnak minősített cikkeket egy többnyelvű sentence-transformer modell (`paraphrase-multilingual-MiniLM-L12-v2`) referencia-leírásokhoz méri; 0,60 feletti koszinusz-hasonlóságnál a cikk felülvizsgálatra kerül. Ha a modell nem elérhető, a lépés kimarad, a pipeline nem áll meg.
4. **Visszacsatolás:** az elemző döntései (Excelben vagy a webes felületen) az adatbázisba kerülnek, és a következő futások pontozását befolyásolják.

Több kulcsszóprofil fut párhuzamosan (a cég és kapcsolódó szervezetei, illetve tévés és rádiós műsorok).

## Felület

- **REST API** (FastAPI): futások indítása és lekérdezése, cikkek szűrése és teljes szöveges keresése (SQLite FTS5), kulcsszavak kezelése, visszajelzések, kulcsszavankénti trend, PDF jelentés futásonként
- **Webes kliens** (React, Vite): cikklista, terminál-nézet, cikk–kulcsszó kapcsolati gráf
- **CLI** (`ikon`): `run`, `scrape`, `score`, `review`, `status`, `export`

## Futtatás

```bash
pip install -e ".[api,dev]"

ikon run                      # teljes pipeline, Excel export az output/ alá
uvicorn ikon.api.app:app      # API + felület, http://localhost:8000
pytest                        # tesztek
```

A frontend külön: `cd frontend && npm ci && npm run dev`. Élesben egyetlen Docker image szolgálja ki mindkettőt (többlépcsős build), Railway-en, perzisztens volume-mal az adatbázisnak és a modell-cache-nek.

## Felépítés

```
ikon/
  scraper.py     gyűjtés
  scoring.py     pontozás és kategorizálás
  embedder.py    szemantikai hasonlóság
  pipeline.py    ETL orchestrátor, futás-audit
  database.py    SQLite séma, migrációk, FTS
  repository.py  adatelérés az API-nak
  api/           FastAPI alkalmazás és routerek
  cli.py         Click CLI
config/          pontozási és gyűjtési paraméterek
migrations/      verziózott SQL migrációk
tests/           pytest (scoring, repository, API végpontok)
frontend/        React kliens
```
