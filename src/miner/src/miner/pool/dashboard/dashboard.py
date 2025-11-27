"""Rich-based dashboard for displaying miner training statistics."""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from datetime import datetime, timezone

from blessed import Terminal
from loguru import logger
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .chart import plot
from .models import DashboardSnapshot
from .utils import IOTA_TITLE, format_bytes


def format_phase(phase: str | None) -> str:
    """Convert phase from LayerPhase.X format to natural language."""
    if not phase:
        return "—"

    # Remove "LayerPhase." prefix if present
    if phase.startswith("LayerPhase."):
        phase = phase.replace("LayerPhase.", "")

    # Convert to natural language
    phase_map = {
        "TRAINING": "Training",
        "WEIGHTS_UPLOADING": "Uploading Weights",
        "MERGING_PARTITIONS": "Merging Partitions",
        "IDLE": "Idle",
        "WAITING": "Waiting",
    }

    return phase_map.get(phase, phase.replace("_", " ").title())


class TrainingDashboard:
    """Rich-based dashboard for displaying miner training statistics."""

    def __init__(self, snapshot_queue: asyncio.Queue[DashboardSnapshot], refresh_interval: float = 1.0):
        self.term = Terminal()
        self.console = Console()
        self.layout = Layout()
        self.snapshot_queue = snapshot_queue
        self.refresh_interval = refresh_interval
        self.start_time = time.time()

        # Data storage
        self.loss_history = deque(maxlen=50)
        self.throughput_history = deque(maxlen=50)
        self.activation_rate_history = deque(maxlen=50)

        # Current state
        self.current_snapshot: DashboardSnapshot | None = None
        self._last_throughput = 0.0
        self._snapshot_timeout_count = 0

        self.setup_layout()

    def setup_layout(self):
        """Configure the dashboard layout structure."""
        # Training statistics full width above plots
        self.layout.split(
            Layout(name="header", size=11),  # Increased to fit IOTA ASCII art (8 lines) + subtitle + borders
            Layout(name="training_statistics", size=10),  # Full width training stats
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )

        # Split main into left (status) and right (charts)
        self.layout["main"].split_row(
            Layout(
                name="left_panel", ratio=1, minimum_size=54
            ),  # Leaderboard and status on left (increased for wider panels)
            Layout(name="right_panel", ratio=3),  # Charts on right
        )

        self.layout["left_panel"].split(
            Layout(name="leaderboard", ratio=1),
            Layout(name="status", ratio=1),
        )

        self.layout["right_panel"].split(
            Layout(name="charts", ratio=1),
        )

        # Shorter charts
        self.layout["charts"].split(
            Layout(name="loss_chart", ratio=1, minimum_size=8),
            Layout(name="throughput_chart", ratio=1, minimum_size=8),
        )

    def generate_header(self):
        """Generate the header panel with IOTA title and network status."""
        snapshot = self.current_snapshot
        if snapshot is None:
            network_status = "Waiting for data..."
        elif snapshot.phase is None:
            network_status = "Initializing (phase=None)"
        else:
            network_status = format_phase(snapshot.phase)
        return Panel(
            Align.center(Text(IOTA_TITLE, style="bold cyan"), vertical="top"),
            subtitle=Text(f"Network Status: {network_status}", style="bold magenta"),
            style="bold white on black",
            width=None,
            padding=(0, 0),
        )

    def generate_metrics(self):
        """Generate the metrics panel with training statistics."""
        snapshot = self.current_snapshot
        if not snapshot:
            return Panel("Waiting for miner data...", title="Training Statistics", border_style="cyan", padding=(0, 1))

        # Create a fixed-width grid for metrics
        grid = Table.grid(padding=(0, 2))
        grid.add_column(width=22)  # Increased for longer labels
        grid.add_column(width=25)  # Increased for longer values
        grid.add_column(width=22)
        grid.add_column(width=25)

        # Model info from snapshot (populated from run info)
        model_name = snapshot.model_name or "IOTA Model"
        architecture = "llama-bottleneck"  # Could be derived from model_name if needed
        num_params = snapshot.total_params
        if num_params is not None:
            # Format params: convert to billions/millions if large
            if num_params >= 1_000_000_000:
                num_params = f"{num_params / 1_000_000_000:.1f}B"
            elif num_params >= 1_000_000:
                num_params = f"{num_params / 1_000_000:.1f}M"
            else:
                num_params = f"{num_params:,}"
        else:
            num_params = snapshot.model_size or "—"
        # Show current layer (0-indexed), not total number of layers
        current_layer = snapshot.layer if snapshot.layer is not None else "—"
        total_layers = snapshot.n_layers if snapshot.n_layers is not None else "—"
        learning_rate = snapshot.learning_rate if snapshot.learning_rate is not None else 1e-5

        grid.add_row(
            Text("Model:", style="cyan"),
            Text(model_name, style="yellow"),
            Text("Architecture:", style="cyan"),
            Text(architecture, style="yellow"),
        )
        grid.add_row(
            Text("Parameters:", style="cyan"),
            Text(num_params, style="yellow"),
            Text("Layer:", style="cyan"),
            Text(str(current_layer), style="yellow"),
        )
        grid.add_row(
            Text("Hotkey:", style="cyan"),
            Text(snapshot.hotkey[:12] + "..." if snapshot.hotkey else "—", style="yellow"),
            Text("Run ID:", style="cyan"),
            Text(snapshot.run_id if snapshot.run_id else "—", style="yellow"),
        )
        grid.add_row(
            Text("Total Layers:", style="cyan"),
            Text(str(total_layers), style="yellow"),
            Text("Activation Rate:", style="cyan"),
            Text(f"{snapshot.activation_rate:.2f} / min", style="yellow"),
        )
        grid.add_row(
            Text("Total Activations:", style="cyan"),
            Text(f"{snapshot.total_activations:,}", style="yellow"),
            Text("Current Loss:", style="cyan"),
            Text(f"{snapshot.latest_loss:.4f}" if snapshot.latest_loss is not None else "—", style="yellow"),
        )
        grid.add_row(
            Text("Avg Loss:", style="cyan"),
            Text(f"{snapshot.loss_average:.4f}" if snapshot.loss_average is not None else "—", style="yellow"),
            Text("", style="cyan"),
            Text("", style="yellow"),
        )
        grid.add_row(
            Text("Downloaded:", style="cyan"),
            Text(format_bytes(snapshot.download_bytes), style="yellow"),
            Text("Uploaded:", style="cyan"),
            Text(format_bytes(snapshot.upload_bytes), style="yellow"),
        )
        grid.add_row(
            Text("Forward Passes:", style="cyan"),
            Text(f"{snapshot.forward_count:,}", style="yellow"),
            Text("Backward Passes:", style="cyan"),
            Text(f"{snapshot.backward_count:,}", style="yellow"),
        )
        grid.add_row(
            Text("Remote Epoch:", style="cyan"),
            Text(str(snapshot.remote_epoch) if snapshot.remote_epoch is not None else "—", style="yellow"),
            Text("Local Epoch:", style="cyan"),
            Text(str(snapshot.local_epoch + 1) if snapshot.local_epoch is not None else "—", style="yellow"),
        )

        return Panel(grid, title="Training Statistics", border_style="cyan", padding=(0, 1), width=None)

    def generate_charts(self):
        """Generate the loss and throughput charts."""
        # Calculate chart width based on terminal width
        try:
            terminal_width = self.term.width or 120
            chart_width = max(50, terminal_width - 45 - 6)
        except Exception:
            chart_width = 70

        # Limit series length to control chart width
        max_series_length = max(10, chart_width - 12 - 3)
        content_width = chart_width

        # Loss chart
        loss_series = (
            list(self.loss_history)[-max_series_length:]
            if len(self.loss_history) > max_series_length
            else list(self.loss_history)
        )
        loss_config = {
            "height": 6,
            "offset": 3,
        }
        loss_chart = plot(loss_series, loss_config)
        if not loss_chart:
            loss_chart_clean = "Waiting for data..."
        else:
            loss_lines = loss_chart.split("\n")
            loss_chart_clean = "\n".join(
                line[:content_width].rstrip() if len(line) > content_width else line.rstrip()
                for line in loss_lines
                if line.strip()
            )
        loss_panel = Panel(
            Text(loss_chart_clean, no_wrap=True, overflow="ignore"),
            title="Training Loss",
            border_style="red",
            width=chart_width + 4,
            padding=(0, 1),
        )

        # Throughput chart
        throughput_series = (
            list(self.throughput_history)[-max_series_length:]
            if len(self.throughput_history) > max_series_length
            else list(self.throughput_history)
        )
        throughput_config = {
            "height": 6,
            "offset": 3,
        }
        throughput_chart = plot(throughput_series, throughput_config)
        if not throughput_chart:
            throughput_chart_clean = "Waiting for data..."
        else:
            throughput_lines = throughput_chart.split("\n")
            throughput_chart_clean = "\n".join(
                line[:content_width].rstrip() if len(line) > content_width else line.rstrip()
                for line in throughput_lines
                if line.strip()
            )
        throughput_panel = Panel(
            Text(throughput_chart_clean, no_wrap=True, overflow="ignore"),
            title="Activation Rate (/min)",
            border_style="green",
            width=chart_width + 4,
            padding=(0, 1),
        )

        return loss_panel, throughput_panel

    def generate_leaderboard(self):
        """Generate the leaderboard panel (showing single miner for now)."""
        snapshot = self.current_snapshot
        if not snapshot:
            return Panel(
                "Waiting for data...", title="Miner Status", border_style="bright_blue", width=73, padding=(0, 1)
            )

        table = Table(
            show_header=True,
            header_style="bold magenta",
            border_style="bright_blue",
            box=None,
            padding=(0, 1),
        )

        table.add_column("Metric", style="cyan", width=22, no_wrap=True)
        table.add_column("Value", justify="right", style="yellow", width=24, no_wrap=True)

        hotkey_display = snapshot.hotkey[:12] + "..." if snapshot.hotkey else "—"
        table.add_row("Hotkey", hotkey_display)
        table.add_row("Layer", str(snapshot.layer) if snapshot.layer is not None else "—")
        table.add_row("Activations", f"{snapshot.total_activations:,}")
        table.add_row("Rate (/min)", f"{snapshot.activation_rate:.2f}")
        if snapshot.latest_loss is not None:
            table.add_row("Latest Loss", f"{snapshot.latest_loss:.4f}")
        if snapshot.loss_average is not None:
            table.add_row("Avg Loss", f"{snapshot.loss_average:.4f}")
        table.add_row("Phase", format_phase(snapshot.phase))
        table.add_row("Needs Pull", "Yes" if snapshot.need_to_pull_weights else "No")

        return Panel(table, title="Miner Status", border_style="bright_blue", width=73, padding=(0, 1))

    def generate_status(self):
        """Generate the status panel with runtime and status message."""
        snapshot = self.current_snapshot
        runtime = time.time() - self.start_time
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)

        table = Table(
            show_header=False,
            border_style="bright_blue",
            box=None,
            padding=(0, 1),
        )

        table.add_column("", style="cyan", width=25, no_wrap=True)
        table.add_column("", justify="right", style="yellow", width=45, no_wrap=True)

        table.add_row("Runtime", f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        if snapshot:
            # Convert UTC to local timezone
            local_time = snapshot.generated_at.astimezone()
            timestamp = local_time.strftime("%H:%M:%S")
            table.add_row("Last Update", timestamp)
            if snapshot.remote_epoch is not None:
                table.add_row("Remote Epoch", str(snapshot.remote_epoch))
            if snapshot.local_epoch is not None:
                table.add_row("Local Epoch", str(snapshot.local_epoch + 1))
            # Show debug info if phase is None
            if snapshot.phase is None:
                debug_info = (
                    f"Phase=None, Layer={snapshot.layer}, RunID={snapshot.run_id[:8] if snapshot.run_id else 'None'}"
                )
                table.add_row("Debug", debug_info)
            status_msg = snapshot.status_message or "Running"
            # Truncate long status messages if needed
            if len(status_msg) > 45:
                status_msg = status_msg[:42] + "..."
            table.add_row("Status", status_msg)
        else:
            queue_size = self.snapshot_queue.qsize()
            debug_msg = f"No snapshot (queue: {queue_size})"
            table.add_row("Debug", debug_msg)

        return Panel(table, title="Status", border_style="bright_blue", width=73, padding=(0, 1))

    def generate_footer(self):
        """Generate the footer panel."""
        footer_text = Text("Press Ctrl+C to exit", style="bold white on blue")
        return Panel(Align.center(footer_text), style="bold white on black", width=None, padding=(0, 1))

    def update_from_snapshot(self, snapshot: DashboardSnapshot):
        """Update dashboard state from a snapshot."""
        self.current_snapshot = snapshot

        # Update loss history
        if snapshot.latest_loss is not None and math.isfinite(snapshot.latest_loss):
            self.loss_history.append(snapshot.latest_loss)
        elif snapshot.loss_average is not None and math.isfinite(snapshot.loss_average):
            self.loss_history.append(snapshot.loss_average)

        # Update throughput history (using activation rate as proxy)
        if math.isfinite(snapshot.activation_rate):
            self.throughput_history.append(snapshot.activation_rate)
            self.activation_rate_history.append(snapshot.activation_rate)

    def render(self):
        """Render the complete dashboard layout."""
        # Update header
        self.layout["header"].update(self.generate_header())

        # Update training statistics (full width above plots)
        self.layout["training_statistics"].update(self.generate_metrics())

        # Update left panel: leaderboard, status
        self.layout["leaderboard"].update(self.generate_leaderboard())
        self.layout["status"].update(self.generate_status())

        # Update right panel: charts
        loss_chart, throughput_chart = self.generate_charts()
        self.layout["loss_chart"].update(loss_chart)
        self.layout["throughput_chart"].update(throughput_chart)

        # Update footer
        self.layout["footer"].update(self.generate_footer())

        return self.layout

    async def run(self):
        """Run the dashboard with live updates."""
        try:
            with Live(self.render(), refresh_per_second=2, screen=True) as live:
                while True:
                    # Poll for new snapshots
                    snapshot: DashboardSnapshot | None = None
                    try:
                        while True:
                            snapshot = self.snapshot_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

                    if snapshot:
                        try:
                            logger.info(
                                f"Dashboard received snapshot: phase={snapshot.phase}, layer={snapshot.layer}, run_id={snapshot.run_id}, activations={snapshot.total_activations}"
                            )
                            self.update_from_snapshot(snapshot)
                        except Exception as e:
                            logger.exception(f"Error updating from snapshot: {e}")
                    else:
                        # If no snapshot received, track timeout
                        self._snapshot_timeout_count += 1
                        queue_size = self.snapshot_queue.qsize()

                        # If we've been waiting a while and queue is empty, something is wrong
                        if self._snapshot_timeout_count > 10 and queue_size == 0:
                            # Create a placeholder snapshot to show something
                            if self.current_snapshot is None or self._snapshot_timeout_count % 20 == 0:
                                try:
                                    from .models import DashboardSnapshot

                                    placeholder = DashboardSnapshot(
                                        generated_at=datetime.now(tz=timezone.utc),
                                        run_id=None,
                                        layer=None,
                                        activation_rate=0.0,
                                        total_activations=0,
                                        latest_loss=None,
                                        loss_average=None,
                                        phase=None,
                                        status_message=f"Waiting for snapshots (timeout: {self._snapshot_timeout_count})",
                                        download_bytes=0,
                                        upload_bytes=0,
                                        forward_count=0,
                                        backward_count=0,
                                    )
                                    self.update_from_snapshot(placeholder)
                                except Exception:
                                    pass

                    try:
                        live.update(self.render())
                    except Exception as e:
                        logger.exception(f"Error rendering dashboard: {e}")
                        # Try to continue with a simple error message
                        try:
                            error_layout = Layout()
                            error_layout.split(
                                Layout(Panel(f"Dashboard rendering error: {e}", style="red"), name="error")
                            )
                            live.update(error_layout)
                        except Exception:
                            pass  # If even error display fails, skip this update

                    await asyncio.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Dashboard stopped.[/]")
        except Exception as e:
            logger.exception(f"Dashboard run error: {e}")
            raise
