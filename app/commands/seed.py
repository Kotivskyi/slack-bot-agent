"""
Seed database with sample data.

This command is a placeholder for future seeding functionality.
"""

import click

from app.commands import command, info


@command("seed", help="Seed database with sample data")
@click.option("--count", "-c", default=10, type=int, help="Number of records to create")
@click.option("--clear", is_flag=True, help="Clear existing data before seeding")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
def seed(
    count: int,
    clear: bool,
    dry_run: bool,
) -> None:
    """
    Seed the database with sample data for development.

    Example:
        project cmd seed --count 50
        project cmd seed --clear --count 100
        project cmd seed --dry-run
    """
    info("No seedable entities configured. Add seeding logic as needed.")
