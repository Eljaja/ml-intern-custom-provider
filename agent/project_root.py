"""Resolve the repository root even when code runs from a venv ``site-packages`` copy."""

from __future__ import annotations

from pathlib import Path

_CONFIG_MARKER = Path("configs") / "main_agent_config.json"


def find_project_root() -> Path:
    """Directory that contains ``configs/main_agent_config.json`` (the real repo root).

    Falls back to ``agent/``'s parent when no marker is found (e.g. partial checkouts).
    """
    start = Path(__file__).resolve().parent
    for d in [start, *start.parents]:
        if (d / _CONFIG_MARKER).is_file():
            return d
    return start.parent
