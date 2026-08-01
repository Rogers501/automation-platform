"""Failure artifact persistence: recorded HTTP exchanges + screenshots.

On test failure, the hooks layer persists captured HTTP exchanges (request +
response) as JSON and triggers a screenshot via the registered provider. All
persistence is best-effort: a failure here must never mask the original test
failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from framework.core.logger import get_logger
from framework.core.recorder import HttpExchange, RequestRecorder
from framework.testing.hooks.screenshot import ScreenshotProvider

__all__ = ["sanitize_node_id", "save_failure_artifacts"]

_NODEID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_node_id(node_id: str) -> str:
    """Convert a pytest node id into a filesystem-safe directory name.

    Args:
        node_id: e.g. ``"tests/test_x.py::test_fail"``.

    Returns:
        A safe name like ``"tests_test_x_py_test_fail"``.
    """
    safe = _NODEID_RE.sub("_", node_id).strip("_")
    return safe or "unknown_test"


def _exchange_to_dict(exchange: HttpExchange) -> dict[str, Any]:
    return asdict(exchange)


def save_failure_artifacts(
    *,
    node_id: str,
    recorder: RequestRecorder | None,
    screenshot_provider: ScreenshotProvider | None,
    artifact_dir: Path,
) -> None:
    """Persist recorded HTTP exchanges (and a screenshot) for a failed test.

    Args:
        node_id: The pytest node id of the failed test.
        recorder: The request recorder holding captured exchanges (may be None).
        screenshot_provider: Optional screenshot provider (no-op if None).
        artifact_dir: Base directory; a per-test subfolder is created under it.
    """
    log = get_logger("artifacts")
    target = artifact_dir / sanitize_node_id(node_id)
    target.mkdir(parents=True, exist_ok=True)

    if recorder is not None and recorder.exchanges:
        path = target / "exchanges.json"
        payload = [_exchange_to_dict(ex) for ex in recorder.exchanges]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("saved {} HTTP exchange(s) to {}", len(payload), path)

    if screenshot_provider is not None:
        try:
            shot = screenshot_provider.screenshot(sanitize_node_id(node_id))
            if shot is not None:
                log.info("saved screenshot to {}", shot)
        except Exception as exc:
            log.warning("screenshot capture failed: {}", exc)
