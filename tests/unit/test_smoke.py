"""Phase 0 smoke tests: assert the framework package is importable and versioned."""

import framework


def test_framework_importable() -> None:
    """The framework package must be importable and expose a version."""
    assert hasattr(framework, "__version__")


def test_framework_version() -> None:
    """The framework must expose the expected version string."""
    assert framework.__version__ == "0.1.0"
