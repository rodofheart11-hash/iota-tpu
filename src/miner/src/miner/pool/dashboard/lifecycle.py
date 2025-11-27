"""Lifecycle management for the dashboard."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from ..stats import StatsTracker
from .dashboard import TrainingDashboard, format_phase
from .models import DashboardSnapshot

if TYPE_CHECKING:  # pragma: no cover - type checking helper
    from ..miner import Miner


class MinerDashboard:
    """Lifecycle manager that streams tracker data into the Rich UI."""

    def __init__(
        self,
        *,
        miner: "Miner",
        tracker: StatsTracker,
        console: Console | None,
        refresh_interval: float = 1.0,
    ) -> None:
        self._miner = miner
        self._tracker = tracker
        self._console = console
        self._refresh_interval = refresh_interval
        self._snapshot_queue: asyncio.Queue[DashboardSnapshot] | None = None
        self._snapshot_task: asyncio.Task[None] | None = None
        self._app_task: asyncio.Task[None] | None = None
        self._dashboard: TrainingDashboard | None = None
        self._stop_event = asyncio.Event()
        self._started = False

    async def start(self) -> None:
        """Start the dashboard."""
        if self._started:
            return

        self._stop_event.clear()
        self._snapshot_queue = asyncio.Queue(maxsize=5)
        self._dashboard = TrainingDashboard(self._snapshot_queue, refresh_interval=self._refresh_interval)

        # Create an initial snapshot to ensure dashboard has data
        # Always create a minimal snapshot first to ensure queue has something
        try:
            minimal_snapshot = DashboardSnapshot(
                generated_at=datetime.now(tz=timezone.utc),
                run_id=None,
                layer=None,
                activation_rate=0.0,
                total_activations=0,
                latest_loss=None,
                loss_average=None,
                phase=None,
                status_message="Dashboard starting...",
                download_bytes=0,
                upload_bytes=0,
                forward_count=0,
                backward_count=0,
            )
            self._snapshot_queue.put_nowait(minimal_snapshot)
            if self._console is not None:
                self._console.print("[green]Initial snapshot created[/]")
        except Exception as e:
            if self._console is not None:
                self._console.print(f"[red]Failed to create initial snapshot: {e}[/]")

        # Try to create a real snapshot, but don't fail if it doesn't work
        try:
            initial_snapshot = self._build_snapshot()
            self._snapshot_queue.put_nowait(initial_snapshot)
            if self._console is not None:
                self._console.print("[green]Real snapshot created[/]")
        except Exception as e:
            if self._console is not None:
                self._console.print(f"[yellow]Failed to create real snapshot (will retry): {type(e).__name__}[/]")
            logger.debug(f"Failed to create initial snapshot: {e}")

        self._snapshot_task = asyncio.create_task(self._snapshot_worker(), name="miner-dashboard-snapshots")
        self._app_task = asyncio.create_task(self._run_dashboard(), name="miner-dashboard-ui")
        self._started = True

        # Output to console if available
        if self._console is not None:
            self._console.print("[green]Dashboard started[/]")
        logger.info("Dashboard started - snapshot worker and UI tasks created")

    async def stop(self) -> None:
        """Stop the dashboard."""
        if not self._started:
            return

        self._stop_event.set()
        tasks = [self._snapshot_task, self._app_task]
        for task in tasks:
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._snapshot_queue = None
        self._snapshot_task = None
        self._app_task = None
        self._dashboard = None
        self._started = False

    async def _run_dashboard(self) -> None:
        """Run the dashboard UI."""
        if self._dashboard is None:
            return
        try:
            await self._dashboard.run()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error_msg = f"Dashboard UI stopped unexpectedly: {type(e).__name__}: {str(e)}"
            logger.exception(error_msg)
            if self._console is not None:
                self._console.print("[red]Dashboard UI encountered an error and was closed.[/]")
                self._console.print(f"[red]Error: {type(e).__name__}: {str(e)}[/]")
                import traceback

                self._console.print("[dim]Traceback:[/]")
                self._console.print(traceback.format_exc())
        finally:
            self._stop_event.set()

    async def _snapshot_worker(self) -> None:
        """Generate snapshots from tracker data."""
        if self._snapshot_queue is None:
            logger.warning("Dashboard snapshot worker: snapshot queue is None")
            if self._console is not None:
                self._console.print("[red]Dashboard snapshot worker: queue is None[/]")
            return
        logger.info("Dashboard snapshot worker started")
        if self._console is not None:
            self._console.print("[yellow]Dashboard snapshot worker started[/]")
        snapshot_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            while not self._stop_event.is_set():
                try:
                    snapshot = self._build_snapshot()
                    snapshot_count += 1
                    consecutive_errors = 0  # Reset error counter on success

                    # Output to console for first snapshot and when phase changes
                    if snapshot_count == 1 or (snapshot.phase and snapshot_count % 20 == 0):
                        phase_info = f"phase={snapshot.phase}" if snapshot.phase else "phase=None (Initializing)"
                        if self._console is not None:
                            self._console.print(
                                f"[dim]Snapshot #{snapshot_count}: {phase_info}, layer={snapshot.layer}, run_id={snapshot.run_id}, activations={snapshot.total_activations}[/]"
                            )
                    if snapshot_count % 10 == 0 or snapshot.phase:  # Log every 10th snapshot or when phase is set
                        logger.info(
                            f"Snapshot worker: built snapshot #{snapshot_count} with phase={snapshot.phase}, layer={snapshot.layer}, run_id={snapshot.run_id}, tracker.current_phase={self._tracker.current_phase}"
                        )
                    await self._publish_snapshot(snapshot)
                except Exception as e:
                    consecutive_errors += 1
                    logger.exception(f"Error building snapshot (error #{consecutive_errors}): {e}")
                    if self._console is not None and consecutive_errors <= 3:
                        self._console.print(
                            f"[red]Snapshot error #{consecutive_errors}: {type(e).__name__}: {str(e)[:50]}[/]"
                        )

                    # Create a minimal snapshot to keep dashboard alive
                    try:
                        minimal_snapshot = DashboardSnapshot(
                            generated_at=datetime.now(tz=timezone.utc),
                            run_id=None,
                            layer=None,
                            activation_rate=0.0,
                            total_activations=0,
                            latest_loss=None,
                            loss_average=None,
                            phase=None,
                            status_message=f"Error building snapshot ({consecutive_errors} errors)",
                            download_bytes=0,
                            upload_bytes=0,
                            forward_count=0,
                            backward_count=0,
                        )
                        await self._publish_snapshot(minimal_snapshot)
                    except Exception as e2:
                        logger.debug(f"Failed to create minimal snapshot: {e2}")
                        # Skip this cycle if even minimal snapshot fails

                    # If too many consecutive errors, wait longer before retrying
                    if consecutive_errors >= max_consecutive_errors:
                        await asyncio.sleep(self._refresh_interval * 2)
                    else:
                        await asyncio.sleep(self._refresh_interval)
                else:
                    await asyncio.sleep(self._refresh_interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Dashboard snapshot worker crashed: {e}")
            if self._console is not None:
                self._console.print(f"[red]Dashboard snapshot worker crashed: {type(e).__name__}: {str(e)[:100]}[/]")
            self._stop_event.set()
        finally:
            self._stop_event.set()
            if self._console is not None:
                self._console.print("[red]Dashboard snapshot worker stopped[/]")

    async def _publish_snapshot(self, snapshot: DashboardSnapshot) -> None:
        """Publish a snapshot to the queue."""
        if self._snapshot_queue is None:
            logger.warning("Dashboard: Cannot publish snapshot, queue is None")
            return
        try:
            self._snapshot_queue.put_nowait(snapshot)
            logger.debug(f"Dashboard: Published snapshot to queue (queue size: {self._snapshot_queue.qsize()})")
        except asyncio.QueueFull:
            try:
                self._snapshot_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await self._snapshot_queue.put(snapshot)
            logger.debug(
                f"Dashboard: Published snapshot after clearing queue (queue size: {self._snapshot_queue.qsize()})"
            )

    def _build_snapshot(self) -> DashboardSnapshot:
        """Build a snapshot from the current tracker state."""
        tracker = self._tracker
        loss_summary = tracker.loss_summary() or {}
        layer = tracker.current_layer
        run_id = tracker.run_id
        phase = tracker.current_phase
        state_manager = getattr(self._miner, "state_manager", None)
        if layer is None and state_manager is not None:
            layer = getattr(state_manager, "layer", None)
        if run_id is None and state_manager is not None:
            run_id = getattr(state_manager, "run_id", None)
        need_to_pull = bool(getattr(self._miner, "need_to_pull_weights", False))

        # Debug logging (can be removed later)
        if phase is None:
            logger.debug(
                f"Dashboard snapshot: phase=None, layer={layer}, run_id={run_id}, tracker.current_phase={tracker.current_phase}"
            )

        # Extract model information from model_manager
        model_name = None
        model_size = None
        total_params = None
        n_splits = None  # Number of layer splits (what miners are assigned to)
        learning_rate = None

        try:
            model_manager = getattr(self._miner, "model_manager", None)
            if model_manager is not None:
                model_config = getattr(model_manager, "model_config", None)
                model_metadata = getattr(model_manager, "model_metadata", None)

                if model_config:
                    # Handle both dict and object access
                    try:
                        if isinstance(model_config, dict):
                            model_name = model_config.get("model_name")
                            total_params = model_config.get("total_global_params")
                        else:
                            model_name = getattr(model_config, "model_name", None)
                            total_params = getattr(model_config, "total_global_params", None)
                    except Exception as e:
                        logger.debug(f"Failed to extract model_config: {e}")

                if model_metadata:
                    # Handle both dict and object access
                    try:
                        if isinstance(model_metadata, dict):
                            model_size = model_metadata.get("model_size")
                            n_splits = model_metadata.get("n_splits")  # Number of layer splits
                            lr_metadata = model_metadata.get("lr")
                            if lr_metadata and isinstance(lr_metadata, dict):
                                learning_rate = lr_metadata.get("learning_rate")
                        else:
                            # Object access
                            model_size = getattr(model_metadata, "model_size", None)
                            n_splits = getattr(model_metadata, "n_splits", None)
                            lr_metadata = getattr(model_metadata, "lr", None)
                            if lr_metadata:
                                learning_rate = getattr(lr_metadata, "learning_rate", None)
                    except Exception as e:
                        logger.debug(f"Failed to extract model_metadata: {e}")
        except Exception as e:
            logger.debug(f"Failed to access model_manager: {e}")

        return DashboardSnapshot(
            generated_at=datetime.now(tz=timezone.utc),
            run_id=run_id,
            layer=layer,
            activation_rate=tracker.activation_rate(),
            total_activations=tracker.total_activations,
            latest_loss=loss_summary.get("latest"),
            loss_average=loss_summary.get("avg"),
            download_bytes=tracker.download_bytes,
            upload_bytes=tracker.upload_bytes,
            forward_count=tracker.forward_count,
            backward_count=tracker.backward_count,
            remote_epoch=tracker.remote_epoch,
            local_epoch=tracker.local_epoch,
            hotkey=getattr(self._miner, "hotkey", None),
            need_to_pull_weights=need_to_pull,
            phase=phase,
            status_message=self._describe_status(tracker, need_to_pull),
            model_name=model_name,
            model_size=model_size,
            total_params=total_params,
            n_layers=n_splits,  # Using n_splits (number of layer splits) instead of n_layers
            learning_rate=learning_rate,
        )

    def _describe_status(self, tracker: StatsTracker, need_to_pull: bool) -> str:
        """Generate a human-readable status message."""
        parts: list[str] = []
        if tracker.current_phase:
            parts.append(f"Phase {format_phase(tracker.current_phase)}")
        if need_to_pull:
            parts.append("Needs weight pull")
        if not parts:
            return "Collecting miner metrics…"
        return " · ".join(parts)
