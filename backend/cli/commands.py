"""Project management CLI."""
# ruff: noqa: E402 - Import at bottom to avoid circular imports

import click
from tabulate import tabulate


@click.group()
@click.version_option(version="0.1.0", prog_name="slack_analytics_app")
def cli():
    """slack_analytics_app management CLI."""
    pass


# === Server Commands ===
@cli.group("server")
def server_cli():
    """Server commands."""
    pass


@server_cli.command("run")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def server_run(host: str, port: int, reload: bool):
    """Run the development server."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@server_cli.command("routes")
def server_routes():
    """Show all registered routes."""
    from app.main import app

    routes = []
    for route in app.routes:
        if hasattr(route, "methods"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                routes.append([method, route.path, getattr(route, "name", "-")])

    click.echo(tabulate(routes, headers=["Method", "Path", "Name"]))


# === Database Commands ===
@cli.group("db")
def db_cli():
    """Database commands."""
    pass


@db_cli.command("init")
def db_init():
    """Initialize the database (run all migrations)."""
    from alembic import command
    from alembic.config import Config

    click.echo("Initializing database...")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    click.secho("Database initialized.", fg="green")


@db_cli.command("migrate")
@click.option("-m", "--message", required=True, help="Migration message")
def db_migrate(message: str):
    """Create a new migration."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, message=message, autogenerate=True)
    click.secho(f"Migration created: {message}", fg="green")


@db_cli.command("upgrade")
@click.option("--revision", default="head", help="Revision to upgrade to")
def db_upgrade(revision: str):
    """Run database migrations."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, revision)
    click.secho(f"Upgraded to: {revision}", fg="green")


@db_cli.command("downgrade")
@click.option("--revision", default="-1", help="Revision to downgrade to")
def db_downgrade(revision: str):
    """Rollback database migrations."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, revision)
    click.secho(f"Downgraded to: {revision}", fg="green")


@db_cli.command("current")
def db_current():
    """Show current migration revision."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.current(alembic_cfg)


@db_cli.command("history")
def db_history():
    """Show migration history."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.history(alembic_cfg)


# === Custom Commands ===
@cli.group("cmd")
def cmd_cli():
    """Custom commands."""
    pass


# Register all custom commands from app/commands/
from app.commands import register_commands

register_commands(cmd_cli)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
