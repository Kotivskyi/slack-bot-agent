"""
Seed database with sample data.

This command populates the app_metrics table with realistic test data
for development and testing of the analytics chatbot.
"""

import asyncio
import random
from datetime import date, timedelta
from decimal import Decimal

import click

from app.commands import command, error, info, success
from app.db.models.app_metrics import AppMetrics
from app.db.session import get_db_context

# Sample data configuration
APPS = [
    ("Paint for Android", "Android"),
    ("Paint for iOS", "iOS"),
    ("Countdown Android", "Android"),
    ("Countdown iOS", "iOS"),
    ("Weather Pro Android", "Android"),
    ("Weather Pro iOS", "iOS"),
    ("Fitness Tracker", "Android"),
    ("Fitness Tracker", "iOS"),
    ("Photo Editor Plus", "Android"),
    ("Photo Editor Plus", "iOS"),
    ("Music Player", "Android"),
    ("Music Player", "iOS"),
    ("Task Manager", "Android"),
    ("Task Manager", "iOS"),
    ("Recipe Book", "Android"),
    ("Recipe Book", "iOS"),
]

COUNTRIES = [
    "USA",
    "United Kingdom",
    "Germany",
    "France",
    "Japan",
    "Canada",
    "Australia",
    "Brazil",
    "India",
    "Mexico",
]


def generate_metrics(
    app_name: str,
    platform: str,
    metric_date: date,
    country: str,
) -> dict:
    """Generate realistic metrics for an app on a given date."""
    # Base values vary by platform (iOS typically higher revenue per user)
    is_ios = platform == "iOS"
    base_installs = random.randint(100, 5000)
    base_revenue_multiplier = 1.5 if is_ios else 1.0

    # Weekend boost for installs
    is_weekend = metric_date.weekday() >= 5
    weekend_multiplier = 1.3 if is_weekend else 1.0

    # Country multipliers (US/UK typically higher revenue)
    country_multipliers = {
        "USA": 2.0,
        "United Kingdom": 1.8,
        "Germany": 1.5,
        "France": 1.4,
        "Japan": 1.6,
        "Canada": 1.5,
        "Australia": 1.4,
        "Brazil": 0.8,
        "India": 0.5,
        "Mexico": 0.7,
    }
    country_mult = country_multipliers.get(country, 1.0)

    installs = int(base_installs * weekend_multiplier * random.uniform(0.7, 1.3))
    in_app_revenue = round(
        Decimal(str(installs * 0.05 * base_revenue_multiplier * country_mult * random.uniform(0.5, 2.0))),
        2,
    )
    ads_revenue = round(
        Decimal(str(installs * 0.02 * country_mult * random.uniform(0.3, 1.5))),
        2,
    )
    ua_cost = round(
        Decimal(str(installs * 0.03 * country_mult * random.uniform(0.4, 1.2))),
        2,
    )

    return {
        "app_name": app_name,
        "platform": platform,
        "date": metric_date,
        "country": country,
        "installs": installs,
        "in_app_revenue": in_app_revenue,
        "ads_revenue": ads_revenue,
        "ua_cost": ua_cost,
    }


async def seed_data(days: int, clear: bool, dry_run: bool) -> int:
    """Seed the database with sample app metrics data."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    records = []
    current_date = start_date

    while current_date <= end_date:
        for app_name, platform in APPS:
            for country in COUNTRIES:
                metrics = generate_metrics(app_name, platform, current_date, country)
                records.append(metrics)
        current_date += timedelta(days=1)

    if dry_run:
        info(f"Would create {len(records)} records")
        info(f"Date range: {start_date} to {end_date}")
        info(f"Apps: {len(APPS)}")
        info(f"Countries: {len(COUNTRIES)}")
        return len(records)

    async with get_db_context() as db:
        if clear:
            from sqlalchemy import delete

            await db.execute(delete(AppMetrics))
            info("Cleared existing app_metrics data")

        # Bulk insert for efficiency
        db.add_all([AppMetrics(**record) for record in records])
        await db.commit()

    return len(records)


@command("seed", help="Seed database with sample app metrics data")
@click.option("--days", "-d", default=90, type=int, help="Number of days of data to generate (default: 90)")
@click.option("--clear", is_flag=True, help="Clear existing data before seeding")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
def seed(
    days: int,
    clear: bool,
    dry_run: bool,
) -> None:
    """
    Seed the database with sample app metrics data for development.

    Generates realistic mobile app analytics data including:
    - Multiple apps across iOS and Android platforms
    - Daily metrics for installs, revenue, and UA costs
    - Data across multiple countries

    Example:
        uv run slack_analytics_app cmd seed
        uv run slack_analytics_app cmd seed --days 30
        uv run slack_analytics_app cmd seed --clear --days 180
        uv run slack_analytics_app cmd seed --dry-run
    """
    try:
        count = asyncio.run(seed_data(days, clear, dry_run))
        if dry_run:
            success(f"Dry run complete. Would create {count} records.")
        else:
            success(f"Successfully seeded {count} records into app_metrics table.")
    except Exception as e:
        error(f"Failed to seed database: {e}")
        raise SystemExit(1) from e
