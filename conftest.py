"""Root pytest configuration for the automation platform.

The framework is installed as an editable workspace member via ``uv sync``, so
``import framework`` resolves without path manipulation. System-specific
conftests live under ``projects/<system>/``.

``pytester`` is enabled so the framework's own pytest plugin (fixtures/hooks)
can be exercised end-to-end in integration tests.
"""

pytest_plugins = ["pytester"]
