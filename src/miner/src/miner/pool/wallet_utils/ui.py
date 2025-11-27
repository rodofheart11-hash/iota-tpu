"""UI helpers for the pool miner CLI."""

from __future__ import annotations

from typing import Iterable

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

__all__ = ["IOTA_ASCII_ART", "clear_screen_with_banner", "print_centered", "prompt_ask_centered", "render_ascii_banner"]

IOTA_ASCII_ART = (
    "▄█   ▄██████▄      ███        ▄████████ \n"
    "███  ███    ███ ▀█████████▄   ███    ███ \n"
    "███▌ ███    ███    ▀███▀▀██   ███    ███ \n"
    "███▌ ███    ███     ███   ▀   ███    ███ \n"
    "███▌ ███    ███     ███     ▀███████████ \n"
    "███  ███    ███     ███       ███    ███ \n"
    "███  ███    ███     ███       ███    ███ \n"
    "█▀    ▀██████▀     ▄████▀     ███    █▀"
)


def print_centered(console: Console, renderable) -> None:
    """Center any renderable or string output on the provided console."""
    if isinstance(renderable, str):
        renderable = Text.from_markup(renderable)
        renderable.justify = "center"
    console.print(Align.center(renderable))


def prompt_ask_centered(
    console: Console,
    prompt: str,
    *,
    choices: Iterable[str] | None = None,
    default: str | None = None,
) -> str:
    """Centered variant of Prompt.ask that preserves Rich markup."""
    print_centered(console, prompt)

    width = getattr(console.size, "width", console.width)
    prompt_indicator = "➤ "
    padding = max((width - len(prompt_indicator)) // 2, 0)
    padded_indicator = f"{' ' * padding}{prompt_indicator}"

    return Prompt.ask(
        padded_indicator,
        choices=list(choices) if choices is not None else None,
        default=default,
        console=console,
    ).strip()


def render_ascii_banner(console: Console, subtitle: str | None = None) -> None:
    """Render the IOTA ASCII art banner centered on the terminal."""
    art_panel = Panel(
        Text(IOTA_ASCII_ART, justify="center", style="cyan"),
        title="[bold magenta]Miner Pool Miner[/]",
        border_style="magenta",
        subtitle=subtitle,
        expand=False,
    )
    print_centered(console, art_panel)
    console.print()


def clear_screen_with_banner(console: Console, subtitle: str | None = None) -> None:
    """Clear the console and redraw the ASCII banner so it stays at the top."""
    console.clear()
    render_ascii_banner(console, subtitle=subtitle)
