"""App automation client (Appium).

Public API: ``AppClient`` for async mobile app automation.

The ``appium-python-client`` package is imported lazily; the framework does
not hard-depend on it at import time. All blocking calls are dispatched via
:func:`asyncio.to_thread` (rule 16).
"""

from framework.clients.app.client import AppClient

__all__ = ["AppClient"]
