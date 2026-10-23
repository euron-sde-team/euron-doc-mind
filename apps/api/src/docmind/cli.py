"""Operator command line.

docmind migrate
docmind user create --email you@example.com --name "You" --admin
docmind demo seed
docmind reindex --workspace northwind
docmind openapi --out docs/api/openapi.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from docmind.core.config import get_settings
from docmind.core.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="Euron DocMind command line.", add_completion=False)
user_app = typer.Typer(no_args_is_help=True, help="Manage accounts.")
demo_app = typer.Typer(no_args_is_help=True, help="Demo data for local stacks.")
app.add_typer(user_app, name="user")
app.add_typer(demo_app, name="demo")


@app.callback()
def _setup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, "console")


@app.command()
def migrate() -> None:
    """Apply pending database migrations."""
    from docmind.db.migrate import migrate as run

    asyncio.run(run(get_settings().database_url))
    typer.echo("migrations applied")


@user_app.command("create")
def create_user(
    email: Annotated[str, typer.Option(help="Sign-in email.")],
    name: Annotated[str, typer.Option(help="Display name.")],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
    admin: Annotated[bool, typer.Option(help="Instance administrator.")] = False,
) -> None:
    """Create an account."""
    from docmind.db.session import Database
    from docmind.services.users import create_user as create

    async def run() -> None:
        db = Database(get_settings())
        try:
            async with db.session() as session:
                user = await create(
                    session, email=email, name=name, password=password, is_admin=admin
                )
                typer.echo(f"created {user.email} ({user.id})")
        finally:
            await db.dispose()

    asyncio.run(run())


@demo_app.command("seed")
def seed(
    samples: Annotated[Path, typer.Option(help="Folder of sample documents.")] = Path("samples"),
    password: Annotated[
        str | None, typer.Option(envvar="DEMO_PASSWORD", help="Password for every demo account.")
    ] = None,
    questions: Annotated[bool, typer.Option(help="Ask the demo questions after indexing.")] = True,
) -> None:
    """Demo accounts, two workspaces, the sample documents and a few conversations."""
    from docmind.demo.seed import run

    settings = get_settings()
    if settings.is_production:
        raise typer.BadParameter("refusing to seed demo data with APP_ENV=production")
    secret = password or (
        settings.demo_password.get_secret_value() if settings.demo_password else None
    )
    if not secret:
        raise typer.BadParameter("set DEMO_PASSWORD (make env generates one)")
    asyncio.run(run(settings, samples, secret, ask_questions=questions))


@app.command()
def reindex(
    workspace: Annotated[str | None, typer.Option(help="Workspace slug; all when omitted.")] = None,
) -> None:
    """Queue every document (of one workspace) for parsing and indexing again."""
    from docmind.demo.seed import reindex as run

    count = asyncio.run(run(get_settings(), workspace))
    typer.echo(f"queued {count} document(s)")


@app.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the OpenAPI document.")] = Path(
        "openapi.json"
    ),
) -> None:
    """Export the OpenAPI document generated from the routes."""
    from docmind.main import create_app

    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
