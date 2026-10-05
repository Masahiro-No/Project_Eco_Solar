from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ReviewStatus = Literal["rejected", "accepted"]
ReviewReason = Literal["blank", "partial", "artifact", "glare", "other"]


class FrameReview(BaseModel):
    status: ReviewStatus
    reason: Optional[str] = None
    reviewed_by: str
    reviewed_at: Optional[datetime] = None


class FrameItem(BaseModel):
    timestamp: datetime = Field(..., description="Scan time (UTC)")
    cloud_pct: Optional[float] = Field(None, description="Cloud cover in the 5x5 px AOI; null when the sun is too low")
    brightness: float = Field(..., description="Mean brightness of the crop, 0-1")
    flags: list[str] = Field(default_factory=list, description="Automatic hints: blank, partial, saturated, jump")
    image_b64: str = Field(..., description="The 64x64 PNG, base64")
    review: Optional[FrameReview] = None


class FrameListResponse(BaseModel):
    station_id: str
    date: str
    timezone: str = "Asia/Bangkok"
    daytime_frames: int
    night_frames: int = Field(..., description="Frames taken with the sun down: black by nature, not shown")
    flagged: int
    rejected: int
    frames: list[FrameItem]


class ReviewItem(BaseModel):
    timestamp: datetime
    status: ReviewStatus
    reason: Optional[ReviewReason] = None


class SubmitReviewsRequest(BaseModel):
    station_id: str
    items: list[ReviewItem] = Field(..., min_length=1, max_length=300)


class SubmitReviewsResponse(BaseModel):
    station_id: str
    saved: int
    rejected: int
    accepted: int


class ConvLstmStatusResponse(BaseModel):
    """What the retrain trigger sees, plus the deployed model and the last retrain."""

    retrain_enabled: bool
    batch_size: Optional[int] = None
    new_scans: Optional[int] = None
    newest_scan: Optional[str] = None
    checked_at: Optional[str] = None
    model_version: Optional[str] = None
    retrained_at: Optional[str] = None
    last_result: Optional[dict] = None
    rejected_frames_total: int = 0
