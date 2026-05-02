from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from post_relay.config import load_config
from post_relay.db import connect_db, initialize_db
from post_relay.indexer import index_photo_sources
from post_relay.repository import get_library_stats

app = typer.Typer(help="Post Relay local-first Instagram content workflow.")
db_app = typer.Typer(help="Database commands.")
index_app = typer.Typer(help="Media indexing commands.")
library_app = typer.Typer(help="Library inspection commands.")
app.add_typer(db_app, name="db")
app.add_typer(index_app, name="index")
app.add_typer(library_app, name="library")

DEFAULT_DB_PATH = Path("data/post_relay.sqlite")


@app.command()
def version() -> None:
    """Print the current Post Relay version."""
    typer.echo("post-relay 0.1.0")


@db_app.command("init")
def db_init(db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path.")) -> None:
    """Initialize the SQLite database."""
    connection = connect_db(db)
    initialize_db(connection)
    typer.echo(f"Initialized database at {db}")


@index_app.command("scan")
def index_scan(
    config: Path = typer.Option(..., "--config", help="Path to photo_sources.yaml."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Scan configured photo sources and persist discovered media."""
    loaded_config = load_config(config)
    connection = connect_db(db)
    initialize_db(connection)
    result = index_photo_sources(connection, loaded_config)
    source_plural = "" if result.source_count == 1 else "s"
    typer.echo(
        f"Indexed {result.scanned_count} photos from {result.source_count} source{source_plural}."
    )


@library_app.command("stats")
def library_stats(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path."),
) -> None:
    """Print basic library statistics."""
    connection = connect_db(db)
    initialize_db(connection)
    stats = get_library_stats(connection)
    typer.echo(f"Total photos: {stats.total_photos}")
    if stats.by_source:
        typer.echo("By source:")
        for source_name, count in stats.by_source.items():
            typer.echo(f"  {source_name}: {count}")
    if stats.by_year:
        typer.echo("By year:")
        for year, count in stats.by_year.items():
            year_label: Optional[int | str] = year if year is not None else "unknown"
            typer.echo(f"  {year_label}: {count}")
