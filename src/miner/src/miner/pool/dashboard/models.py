"""Data models for the dashboard."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class DashboardSnapshot:
    """Serializable view of dashboard data sourced from the miner."""

    generated_at: datetime
    run_id: Optional[str]
    layer: Optional[int]
    activation_rate: float
    total_activations: int
    latest_loss: Optional[float]
    loss_average: Optional[float]
    download_bytes: int = 0
    upload_bytes: int = 0
    forward_count: int = 0
    backward_count: int = 0
    remote_epoch: Optional[int] = None
    local_epoch: Optional[int] = None
    hotkey: Optional[str] = None
    need_to_pull_weights: bool = False
    phase: Optional[str] = None
    status_message: str = ""
    model_name: Optional[str] = None
    model_size: Optional[str] = None
    total_params: Optional[int] = None
    n_layers: Optional[int] = None  # Number of layer splits (n_splits from model_metadata)
    learning_rate: Optional[float] = None
