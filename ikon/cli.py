"""
Click-alapú CLI – az `ikon` parancs belépési pontja.

Elérhető parancsok:
    ikon run            Teljes pipeline futtatása (scrape → score → export)
    ikon scrape         Csak scraping, nyers CSV mentése
    ikon score CSV      Nyers CSV újrapontozása és exportálása
    ikon review XLSX    Emberi döntések beolvasása Excelből → DB
    ikon status         Pipeline futás előzmények
    ikon export RUN_ID  Adott futás exportálása Excelbe (DB-ből)
"""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ikon.config import load_config
from ikon.database import Database

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# CLI csoport
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="ikon-monitor")
def cli() -> None:
    """IKO Média Monitoring – heti sajtóelemzés pipeline."""


# ---------------------------------------------------------------------------
# ikon run
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--from-cache", "from_cache", type=click.Path(exists=True), default=None,
              metavar="CSV", help="Meglévő nyers CSV újrapontozása scraping nélkül")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              metavar="YAML", help="Egyedi konfigurációs fájl")
@click.option("--no-export", is_flag=True, default=False, help="Excel/Parquet export kihagyása")
@click.option("-v", "--verbose", is_flag=True, default=False)
def run(from_cache: str | None, config_path: str | None, no_export: bool, verbose: bool) -> None:
    """Teljes pipeline: scraping → scoring → export."""
    _setup_logging(verbose)
    cfg = load_config(Path(config_path) if config_path else None)

    from ikon.pipeline import run_pipeline

    console.print("[bold cyan]IKO Media Monitor – pipeline indul...[/bold cyan]")

    pipeline_run, articles, raw_articles = run_pipeline(
        cfg,
        from_cache=Path(from_cache) if from_cache else None,
    )

    if not no_export:
        from ikon.exporter import export_excel, export_parquet

        today = date.today().isoformat()
        output_path = Path(cfg.export.output_dir) / f"hirek_{today}.xlsx"
        export_excel(articles, raw_articles, output_path, cfg.export)

        if cfg.export.export_parquet:
            export_parquet(articles, cfg.export.output_dir, pipeline_run.run_id)

        console.print(f"\n[bold green]Excel mentve:[/bold green] {output_path}")

    _print_run_summary(pipeline_run)


# ---------------------------------------------------------------------------
# ikon scrape
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option("-v", "--verbose", is_flag=True, default=False)
def scrape(config_path: str | None, verbose: bool) -> None:
    """Csak scraping – nyers CSV mentése, scoring nélkül."""
    _setup_logging(verbose)
    cfg = load_config(Path(config_path) if config_path else None)

    from ikon.scraper import scrape_all
    from ikon.pipeline import save_raw_to_csv

    console.print("[bold cyan]Scraping indul...[/bold cyan]")
    raw_articles = scrape_all(cfg.scraping)

    today = date.today().isoformat()
    out = Path(cfg.export.output_dir) / f"raw_{today}.csv"
    save_raw_to_csv(raw_articles, out)

    console.print(f"[green]Kész:[/green] {len(raw_articles)} nyers cikk → {out}")


# ---------------------------------------------------------------------------
# ikon score
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option("--no-db", is_flag=True, default=False, help="DB-be nem menti az eredményt")
@click.option("-v", "--verbose", is_flag=True, default=False)
def score(csv_path: str, config_path: str | None, no_db: bool, verbose: bool) -> None:
    """Nyers CSV betöltése és újrapontozása."""
    _setup_logging(verbose)
    cfg = load_config(Path(config_path) if config_path else None)

    from ikon.pipeline import run_pipeline

    console.print(f"[cyan]Scoring:[/cyan] {csv_path}")
    pipeline_run, articles, raw_articles = run_pipeline(cfg, from_cache=Path(csv_path))

    from ikon.exporter import export_excel
    today = date.today().isoformat()
    out = Path(cfg.export.output_dir) / f"hirek_{today}.xlsx"
    export_excel(articles, raw_articles, out, cfg.export)
    console.print(f"[green]Excel mentve:[/green] {out}")
    _print_run_summary(pipeline_run)


# ---------------------------------------------------------------------------
# ikon review
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("excel_path", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option("-v", "--verbose", is_flag=True, default=False)
def review(excel_path: str, config_path: str | None, verbose: bool) -> None:
    """Emberi döntések beolvasása Excelből és mentése az adatbázisba."""
    _setup_logging(verbose)
    cfg = load_config(Path(config_path) if config_path else None)

    from ikon.reviewer import read_decisions_from_excel

    console.print(f"[cyan]Feedback beolvasása:[/cyan] {excel_path}")
    entries = read_decisions_from_excel(Path(excel_path))

    if not entries:
        console.print("[yellow]Nem találtam kitöltött döntést.[/yellow]")
        return

    with Database(cfg.storage.db_path) as db:
        saved = db.upsert_feedback(entries)

    releváns = sum(1 for e in entries if e.decision.value == "releváns")
    nem = sum(1 for e in entries if e.decision.value == "nem_releváns")
    console.print(
        f"[green]Mentve:[/green] {releváns} releváns + {nem} nem releváns "
        f"({saved} bejegyzés összesen)"
    )

    # Teljes feedback statisztika
    with Database(cfg.storage.db_path) as db:
        all_fb = db.load_feedback()
    console.print(f"Adatbázisban összesen: [bold]{len(all_fb)}[/bold] feedback URL")


# ---------------------------------------------------------------------------
# ikon export
# ---------------------------------------------------------------------------

@cli.command("export")
@click.argument("run_id", default="latest")
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option("-v", "--verbose", is_flag=True, default=False)
def export_cmd(run_id: str, config_path: str | None, verbose: bool) -> None:
    """Adott pipeline futás exportálása Excelbe az adatbázisból.

    RUN_ID: Futás azonosítója (pl. 20260616T120000Z) vagy 'latest'.
    """
    _setup_logging(verbose)
    cfg = load_config(Path(config_path) if config_path else None)

    with Database(cfg.storage.db_path) as db:
        if run_id == "latest":
            run_id = db.get_latest_run_id()
            if not run_id:
                console.print("[red]Nincs befejezett pipeline futás az adatbázisban.[/red]")
                raise SystemExit(1)
            console.print(f"Legutóbbi futás: [bold]{run_id}[/bold]")

        rows = db.get_articles_for_run(run_id)

    if not rows:
        console.print(f"[yellow]Nem találtam cikket a(z) {run_id} futáshoz.[/yellow]")
        return

    # DB sorok → ScoredArticle (csak az exporthoz szükséges mezők)
    from ikon.exporter import export_excel
    from ikon.models import ScoredArticle, Category, SourceType, KeywordTier
    import json

    articles = []
    for r in rows:
        try:
            articles.append(ScoredArticle(
                url=r["url"],
                title=r["title"] or "",
                source=r["source"] or "",
                source_type=SourceType(r["source_type"] or "egyéb"),
                published_date=r["published_date"] or "",
                published_time=r["published_time"] or "",
                excerpt=r["excerpt"] or "",
                matched_keywords=json.loads(r["matched_keywords"] or "[]"),
                best_tier=KeywordTier(r["best_tier"] or "tier3_generikus"),
                score=r["score"],
                score_reason=r["score_reason"] or "",
                category=Category(r["category"]),
            ))
        except Exception as exc:
            logger.debug("Sor kihagyva: %s", exc)

    out = Path(cfg.export.output_dir) / f"hirek_{run_id}.xlsx"
    export_excel(articles, [], out, cfg.export)
    console.print(f"[green]Excel mentve:[/green] {out}")


# ---------------------------------------------------------------------------
# ikon status
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True), default=None)
@click.option("-n", "--limit", default=10, show_default=True, help="Megjelenített futások száma")
def status(config_path: str | None, limit: int) -> None:
    """Pipeline futás előzmények."""
    cfg = load_config(Path(config_path) if config_path else None)

    with Database(cfg.storage.db_path) as db:
        history = db.pipeline_history()
        total_feedback = len(db.load_feedback())

    if not history:
        console.print("[yellow]Nincs pipeline futás az adatbázisban.[/yellow]")
        return

    table = Table(title="Pipeline futás előzmények", show_lines=True)
    table.add_column("Run ID", style="cyan")
    table.add_column("Státusz")
    table.add_column("Nyers", justify="right")
    table.add_column("Egyedi", justify="right")
    table.add_column("Releváns", justify="right")
    table.add_column("Fv.", justify="right")
    table.add_column("Zaj", justify="right")
    table.add_column("Duplikátum %", justify="right")

    for row in history[:limit]:
        dup_pct = ""
        if row["total_raw"] and row["total_unique"]:
            dup_pct = f"{round(100*(1 - row['total_unique']/row['total_raw']), 1)}%"
        status_style = "green" if row["status"] == "completed" else "red"
        table.add_row(
            row["run_id"],
            f"[{status_style}]{row['status']}[/{status_style}]",
            str(row["total_raw"] or "–"),
            str(row["total_unique"] or "–"),
            str(row["relevant"] or "–"),
            str(row["review"] or "–"),
            str(row["noise"] or "–"),
            dup_pct,
        )

    console.print(table)
    console.print(f"\nFeedback adatbázisban: [bold]{total_feedback}[/bold] URL")


# ---------------------------------------------------------------------------
# Segédszolgáltatás
# ---------------------------------------------------------------------------

def _print_run_summary(run: "PipelineRun") -> None:
    table = Table(show_header=False, box=None)
    table.add_column("Mező", style="dim")
    table.add_column("Érték", style="bold")
    table.add_row("Run ID", run.run_id)
    table.add_row("Státusz", f"[green]{run.status}[/green]" if run.status == "completed" else f"[red]{run.status}[/red]")
    table.add_row("Nyers cikkek", str(run.total_raw_articles))
    table.add_row("Egyedi URL", str(run.total_unique_articles))
    table.add_row("✅ Releváns", str(run.relevant_count))
    table.add_row("⚠️  Felülvizsgálandó", str(run.review_count))
    table.add_row("❌ Zaj", str(run.noise_count))
    table.add_row("Duplikátum arány", f"{run.duplicate_rate:.1%}")
    console.print(table)
