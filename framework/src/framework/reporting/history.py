"""Allure history preservation for trend reporting.

Copies Allure result files between runs so the generated HTML report shows
historical trends (pass/fail over time). In CI, call
:func:`copy_history_to_results` before generating the report and
:func:`preserve_history` after.

Uses :mod:`shutil` (stdlib) - no external dependencies. All operations are
synchronous; if called from async context, wrap in :func:`asyncio.to_thread`
(rule 16).

Layering: depends only on stdlib + ``core`` logger. Never depends on
``clients`` or ``testing`` (rule 11).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from framework.core.logger import get_logger

__all__ = [
    "copy_history_to_results",
    "preserve_history",
]

_LOGGER = get_logger("allure_history")

#: File extensions that belong to Allure result files.
_RESULT_SUFFIXES = frozenset({".json", ".xml", ".png", ".webm", ".svg", ".txt"})


def _is_result_file(path: Path) -> bool:
    """Return whether ``path`` is an Allure result file."""
    return path.suffix in _RESULT_SUFFIXES


def preserve_history(
    results_dir: Path,
    history_dir: Path,
    *,
    max_runs: int = 20,
) -> int:
    """Copy current Allure results to a history directory for trend tracking.

    Args:
        results_dir: The ``--alluredir`` directory with current results.
        history_dir: Directory to store historical results.
        max_runs: Maximum number of historical runs to keep.

    Returns:
        Number of files copied.
    """
    if not results_dir.exists():
        _LOGGER.warning("Results directory not found: {}", results_dir)
        return 0

    history_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(results_dir.iterdir()):
        if src.is_file() and _is_result_file(src):
            shutil.copy2(src, history_dir / src.name)
            count += 1

    _LOGGER.info("Preserved {} result files to {}", count, history_dir)

    _prune_history(history_dir, max_runs)
    return count


def copy_history_to_results(
    history_dir: Path,
    results_dir: Path,
) -> int:
    """Copy historical results into the current results directory.

    Call this before ``allure generate`` so the report includes trend data.

    Args:
        history_dir: Directory with historical results.
        results_dir: The current ``--alluredir`` directory.

    Returns:
        Number of files copied.
    """
    if not history_dir.exists():
        _LOGGER.debug("No history directory: {}", history_dir)
        return 0

    results_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(history_dir.iterdir()):
        if src.is_file() and _is_result_file(src):
            dst = results_dir / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
                count += 1

    _LOGGER.info("Copied {} history files to results", count)
    return count


def _prune_history(history_dir: Path, max_runs: int) -> None:
    """Keep only the most recent ``max_runs`` result files.

    Allure result files are named with timestamps; older files are removed
    when the count exceeds ``max_runs``.
    """
    files = sorted(
        (f for f in history_dir.iterdir() if f.is_file() and _is_result_file(f)),
        key=lambda p: p.stat().st_mtime,
    )
    excess = len(files) - max_runs
    if excess > 0:
        for f in files[:excess]:
            f.unlink()
        _LOGGER.debug("Pruned {} old history files", excess)
