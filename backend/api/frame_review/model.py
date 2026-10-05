from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class SatelliteFrameReview(Base):
    """A person's verdict on one real satellite frame. Rejected frames are left out of ConvLSTM training."""

    __tablename__ = "satellite_frame_reviews"
    __table_args__ = (UniqueConstraint("station_id", "frame_timestamp", name="uq_frame_review_station_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(String(50), ForeignKey("stations.id"), index=True, nullable=False)
    frame_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)          # rejected | accepted
    reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # blank | partial | artifact | glare | other
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
