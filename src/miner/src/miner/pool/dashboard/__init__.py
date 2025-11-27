"""
Rich-based dashboard for the miner pool runtime.

The dashboard is powered by Rich and renders live miner telemetry sourced
from ``StatsTracker``. Snapshot generation is decoupled from the UI so the
miner can continue operating even if the dashboard is disabled or encounters
an error.
"""

from .dashboard import TrainingDashboard
from .lifecycle import MinerDashboard
from .models import DashboardSnapshot

__all__ = [
    "DashboardSnapshot",
    "MinerDashboard",
    "TrainingDashboard",
]
