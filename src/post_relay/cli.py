from __future__ import annotations

import typer

app = typer.Typer(help="Post Relay local-first Instagram content workflow.")


@app.command()
def version() -> None:
    """Print the current Post Relay version."""
    typer.echo("post-relay 0.1.0")
