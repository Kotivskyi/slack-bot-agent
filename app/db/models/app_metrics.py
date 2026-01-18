"""App metrics database model for analytics data."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AppMetrics(Base):
    """App metrics model for mobile app analytics data.

    Stores daily metrics for mobile apps including installs,
    revenue, and user acquisition costs.
    """

    __tablename__ = "app_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    installs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    in_app_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    ads_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    ua_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<AppMetrics(app_name={self.app_name}, platform={self.platform}, date={self.date})>"
