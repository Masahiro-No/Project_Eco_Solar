from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    panel_area: Mapped[float] = mapped_column(Float, nullable=False)  # Area A in m^2
    efficiency: Mapped[float] = mapped_column(Float, nullable=False)  # Efficiency eta (e.g. 0.185 for 18.5%)
    target_capacity_kw: Mapped[float] = mapped_column(Float, nullable=False)  # Peak / Target Capacity in kW
    
    # Soft-delete fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
