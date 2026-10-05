from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RetrainRun(BaseModel):
    run_id: str = Field(..., description="MLflow run id")
    has_curves: bool = Field(False, description="True when the run logged its per-epoch learning curves")
    started_at: datetime
    outcome: str = Field(..., description="deployed | rejected | unknown")
    reason: Optional[str] = Field(None, description="Why a run was rejected")
    version: Optional[str] = Field(None, description="Model version the run deployed")
    gate: str = Field(..., description="measured_ghi | weather_only | val_mse")
    metric: str = Field(..., description="Metric of the gate: real_mae | val_mae | val_mse")
    before: Optional[float] = Field(None, description="Deployed model on the held-out data")
    after: Optional[float] = Field(None, description="Retrained model on the same data")
    details: dict[str, Any] = Field(default_factory=dict)


class CurvePoint(BaseModel):
    epoch: int
    value: float


class RunCurvesResponse(BaseModel):
    """Learning curves of one retrain run: {metric name: points by epoch}. Epoch 0 is the model before the run."""

    run_id: str
    curves: dict[str, list[CurvePoint]]


class LstmStatus(BaseModel):
    model_version: Optional[str] = None
    trained_at: Optional[str] = None
    lookback_steps: Optional[int] = None
    previous_version: Optional[str] = None
    scheduled: bool = Field(False, description="A retrain is waiting for the debounce delay")
    running: bool = False


class ConvLstmStatus(BaseModel):
    model_version: Optional[str] = None
    retrained_at: Optional[str] = None
    new_scans: Optional[int] = Field(None, description="New daytime scans since the last batch")
    batch_size: Optional[int] = None
    newest_scan: Optional[str] = None
    checked_at: Optional[str] = None
    scheduled: bool = False
    running: bool = False
    rejected_frames_total: int = 0


class RetrainHistory(BaseModel):
    lstm: list[RetrainRun] = Field(default_factory=list)
    convlstm: list[RetrainRun] = Field(default_factory=list)


class RetrainStatusResponse(BaseModel):
    retrain_enabled: bool
    lstm: LstmStatus
    convlstm: ConvLstmStatus
    history: RetrainHistory
    history_error: Optional[str] = Field(None, description="Set when the history could not be read from MLflow")
