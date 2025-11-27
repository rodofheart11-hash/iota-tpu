"""Utilities for parsing `btcli w list --json-out` output."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

__all__ = ["parse_btcli_wallets"]


def parse_btcli_wallets(raw_output: str) -> Dict[str, Any]:
    """Convert JSON output from `btcli w list --json-out` into a nested dictionary."""
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ValueError("btcli output is not valid JSON. Ensure --json-out is supported.") from exc

    coldkey_candidates: Iterable[Any]
    if isinstance(data, dict):
        if isinstance(data.get("coldkeys"), list):
            coldkey_candidates = data["coldkeys"]
        elif isinstance(data.get("wallets"), list):
            coldkey_candidates = data["wallets"]
        else:
            coldkey_candidates = []
    elif isinstance(data, list):
        coldkey_candidates = data
    else:
        coldkey_candidates = []

    result: Dict[str, Any] = {"coldkeys": []}
    for coldkey in coldkey_candidates:
        if not isinstance(coldkey, dict):
            continue
        name = coldkey.get("name") or coldkey.get("coldkey_name") or coldkey.get("wallet_name")
        address = coldkey.get("ss58_address") or coldkey.get("address")
        hotkeys = coldkey.get("hotkeys") or coldkey.get("coldkey_hotkeys") or []
        normalized_hotkeys = []
        for hotkey in hotkeys:
            if not isinstance(hotkey, dict):
                continue
            hotkey_name = hotkey.get("name") or hotkey.get("hotkey_name")
            hotkey_address = hotkey.get("ss58_address") or hotkey.get("address")
            if hotkey_name and hotkey_address:
                normalized_hotkeys.append({"name": hotkey_name, "ss58_address": hotkey_address})

        if name and address:
            result["coldkeys"].append({"name": name, "ss58_address": address, "hotkeys": normalized_hotkeys})

    return result
