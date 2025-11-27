"""Utility functions for the dashboard."""

IOTA_TITLE = """▄█   ▄██████▄      ███        ▄████████
███  ███    ███ ▀█████████▄   ███    ███
███▌ ███    ███    ▀███▀▀██   ███    ███
███▌ ███    ███     ███   ▀   ███    ███
███▌ ███    ███     ███     ▀███████████
███  ███    ███     ███       ███    ███
███  ███    ███     ███       ███    ███
█▀    ▀██████▀     ▄████▀     ███    █▀"""


def format_bytes(value: int) -> str:
    """Convert bytes into a compact human readable string."""

    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(value)
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.2f} {units[-1]}"
