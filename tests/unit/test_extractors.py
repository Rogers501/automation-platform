"""Unit tests for framework.testing.extractors."""

from __future__ import annotations

import importlib.util

import pytest

from framework.core.exceptions import FrameworkError
from framework.testing.extractors import (
    HeaderExtractor,
    JmesPathExtractor,
    JsonPathExtractor,
    compile_extractor,
    extract,
)

_HAS_JMESPATH = importlib.util.find_spec("jmespath") is not None


class TestJsonPathExtractor:
    def test_extract_found(self) -> None:
        ex = JsonPathExtractor("$.data.records[0].id")
        assert ex.extract({"data": {"records": [{"id": 42}]}}) == 42

    def test_extract_missing_raises(self) -> None:
        ex = JsonPathExtractor("$.data.records[0].id")
        with pytest.raises(FrameworkError):
            ex.extract({"data": {}})

    def test_empty_path_raises(self) -> None:
        with pytest.raises(FrameworkError):
            JsonPathExtractor("")


class TestHeaderExtractor:
    def test_case_insensitive(self) -> None:
        ex = HeaderExtractor("X-Trace-Id")
        assert ex.extract({"x-trace-id": "t1", "content-type": "json"}) == "t1"

    def test_missing_raises(self) -> None:
        with pytest.raises(FrameworkError):
            HeaderExtractor("Authorization").extract({"x": "y"})

    def test_non_dict_raises(self) -> None:
        with pytest.raises(FrameworkError):
            HeaderExtractor("Authorization").extract("not-a-dict")


@pytest.mark.skipif(not _HAS_JMESPATH, reason="jmespath not installed")
class TestJmesPathExtractor:
    def test_extract(self) -> None:
        ex = JmesPathExtractor("data.token")
        assert ex.extract({"data": {"token": "abc"}}) == "abc"


class TestCompileAndExtract:
    def test_header_prefix(self) -> None:
        assert isinstance(compile_extractor("header:Authorization"), HeaderExtractor)

    def test_jmes_prefix(self) -> None:
        assert isinstance(compile_extractor("jmes:data.token"), JmesPathExtractor)

    def test_default_is_jsonpath(self) -> None:
        assert isinstance(compile_extractor("$.data.id"), JsonPathExtractor)

    def test_empty_spec_raises(self) -> None:
        with pytest.raises(FrameworkError):
            compile_extractor("")

    def test_extract_one_shot(self) -> None:
        assert extract({"data": {"id": 7}}, "$.data.id") == 7

    def test_extract_header_one_shot(self) -> None:
        assert extract({"x-trace-id": "t9"}, "header:X-Trace-Id") == "t9"
