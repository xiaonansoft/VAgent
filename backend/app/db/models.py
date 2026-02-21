from datetime import datetime
from typing import Any
from sqlalchemy import String, Float, Boolean, JSON, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class Heat(Base):
    __tablename__ = "heats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    heat_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    furnace_id: Mapped[str] = mapped_column(String)
    l1_recipe: Mapped[dict[str, Any]] = mapped_column(JSON)
    l2_final_temp: Mapped[float] = mapped_column(Float)
    equilibrium_final_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_final_temp: Mapped[float] = mapped_column(Float)
    actual_analysis: Mapped[dict[str, Any]] = mapped_column(JSON)
    advice_adopted: Mapped[bool] = mapped_column(Boolean)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(datetime.UTC))
