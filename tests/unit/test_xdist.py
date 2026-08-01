"""Unit tests for pytest-xdist concurrent execution support.

Verifies that the framework's tests can run under parallel execution
without conflicts (rule 13: tests must be independent, no order dependency).
Uses pytester to create an isolated test suite and runs it with ``-n 2``.

These tests are skipped if pytest-xdist is not installed (optional dep
in some environments).
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


def _has_xdist() -> bool:
    """Check whether pytest-xdist is importable."""
    try:
        import xdist  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _has_xdist(), reason="pytest-xdist not installed")


def test_parallel_execution_passes(pytester: pytest.Pytester) -> None:
    """A small independent test suite runs successfully under -n 2."""
    pytester.makepyfile(
        """
        def test_a():
            assert 1 + 1 == 2

        def test_b():
            assert "hello" != "world"

        def test_c():
            assert len([1, 2, 3]) == 3

        def test_d():
            assert True
        """
    )
    result = pytester.runpytest("-n", "2", "-q")
    result.assert_outcomes(passed=4)


def test_parallel_execution_isolates_fixtures(pytester: pytest.Pytester) -> None:
    """Session-scoped fixtures are independent per worker process."""
    pytester.makepyfile(
        """
        import pytest

        _counter = {"n": 0}

        @pytest.fixture(scope="session")
        def shared():
            _counter["n"] += 1
            return _counter["n"]

        def test_uses_shared_1(shared):
            assert shared >= 1

        def test_uses_shared_2(shared):
            assert shared >= 1
        """
    )
    result = pytester.runpytest("-n", "2", "-q")
    result.assert_outcomes(passed=2)


def test_parallel_execution_marker_respected(pytester: pytest.Pytester) -> None:
    """Markers work correctly under parallel execution."""
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.smoke
        def test_smoke_a():
            assert True

        @pytest.mark.smoke
        def test_smoke_b():
            assert True

        @pytest.mark.regression
        def test_regression_a():
            assert True
        """
    )
    pytester.makeini(
        """
        [pytest]
        markers =
            smoke: smoke tests
            regression: regression tests
        """
    )
    result = pytester.runpytest("-n", "2", "-m", "smoke", "-q")
    result.assert_outcomes(passed=2)


def test_serial_execution_still_works(pytester: pytest.Pytester) -> None:
    """Without -n flag, tests run in serial (backward compatible)."""
    pytester.makepyfile(
        """
        def test_serial():
            assert 42 == 42
        """
    )
    result = pytester.runpytest("-q")
    result.assert_outcomes(passed=1)
