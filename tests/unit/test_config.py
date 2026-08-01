"""Unit tests for framework.core.config (hermetic: no real files/network)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from framework.core.config import (
    AppEnv,
    FrameworkSettings,
    HttpSettings,
    YamlEnvSettingsSource,
    get_settings,
    reset_settings,
)
from framework.core.exceptions import ConfigError


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Clear all APP_ env vars, redirect config dir to tmp, reset settings cache."""
    for key in list(os.environ):
        if key.startswith("APP_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_CONFIG_DIR", str(tmp_path))
    reset_settings()
    yield
    reset_settings()


def _write_yaml(directory: Path, env: str, body: str) -> Path:
    """Write a YAML config file for ``env`` into ``directory``."""
    path = directory / f"{env}.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_appenv_values() -> None:
    """AppEnv exposes the four supported environments."""
    assert AppEnv.DEV.value == "dev"
    assert AppEnv.TEST.value == "test"
    assert AppEnv.UAT.value == "uat"
    assert AppEnv.PROD.value == "prod"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dev", AppEnv.DEV),
        ("DEV", AppEnv.DEV),
        ("Test", AppEnv.TEST),
        ("uat", AppEnv.UAT),
        ("PROD", AppEnv.PROD),
        (" prod ", AppEnv.PROD),
    ],
)
def test_appenv_from_string_valid(raw: str, expected: AppEnv) -> None:
    """from_string is case-insensitive and tolerates surrounding whitespace."""
    assert AppEnv.from_string(raw) == expected


def test_appenv_from_string_invalid() -> None:
    """An unknown environment name raises ConfigError."""
    with pytest.raises(ConfigError):
        AppEnv.from_string("staging")


def test_appenv_from_string_non_string() -> None:
    """A non-string value raises ConfigError."""
    with pytest.raises(ConfigError):
        AppEnv.from_string(123)  # type: ignore[arg-type]


def test_defaults_when_no_yaml_no_env() -> None:
    """With no YAML and no env vars, field defaults apply."""
    settings = FrameworkSettings()
    assert settings.name == "automation-platform"
    assert settings.env is AppEnv.DEV
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert isinstance(settings.http, HttpSettings)
    assert settings.http.base_url == ""


def test_yaml_overrides_defaults(tmp_path: Path) -> None:
    """The dev YAML file overrides model defaults."""
    _write_yaml(tmp_path, "dev", "env: dev\ndebug: true\nlog_level: DEBUG\n")
    settings = FrameworkSettings()
    assert settings.env is AppEnv.DEV
    assert settings.debug is True
    assert settings.log_level == "DEBUG"


def test_env_var_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_LOG_LEVEL env var beats the YAML value."""
    _write_yaml(tmp_path, "dev", "env: dev\nlog_level: DEBUG\n")
    monkeypatch.setenv("APP_LOG_LEVEL", "WARNING")
    settings = FrameworkSettings()
    assert settings.log_level == "WARNING"


def test_env_var_overrides_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_NAME env var beats the default name."""
    monkeypatch.setenv("APP_NAME", "custom-platform")
    settings = FrameworkSettings()
    assert settings.name == "custom-platform"


def test_app_env_selects_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_ENV selects which YAML file is loaded."""
    _write_yaml(tmp_path, "prod", "env: prod\ndebug: false\nlog_level: WARNING\n")
    _write_yaml(tmp_path, "dev", "env: dev\ndebug: true\nlog_level: DEBUG\n")
    monkeypatch.setenv("APP_ENV", "prod")
    settings = FrameworkSettings()
    assert settings.env is AppEnv.PROD
    assert settings.log_level == "WARNING"


def test_invalid_app_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid APP_ENV raises ConfigError at source construction."""
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ConfigError):
        FrameworkSettings()


def test_missing_yaml_uses_defaults() -> None:
    """A missing YAML file is tolerated; defaults apply."""
    settings = FrameworkSettings()
    assert settings.env is AppEnv.DEV
    assert settings.debug is False


def test_yaml_non_mapping_raises(tmp_path: Path) -> None:
    """A YAML file whose top-level is not a mapping raises ConfigError."""
    _write_yaml(tmp_path, "dev", "- a\n- b\n")
    with pytest.raises(ConfigError):
        FrameworkSettings()


def test_init_kwargs_highest_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Init kwargs beat both env vars and YAML."""
    _write_yaml(tmp_path, "dev", "env: dev\nlog_level: DEBUG\n")
    monkeypatch.setenv("APP_LOG_LEVEL", "WARNING")
    settings = FrameworkSettings(log_level="ERROR", debug=True)
    assert settings.log_level == "ERROR"
    assert settings.debug is True


def test_yaml_nested_http_section(tmp_path: Path) -> None:
    """Nested http settings load from YAML."""
    _write_yaml(
        tmp_path,
        "dev",
        "env: dev\nhttp:\n  base_url: http://example.test\n  read_timeout: 5.0\n",
    )
    settings = FrameworkSettings()
    assert settings.http.base_url == "http://example.test"
    assert settings.http.read_timeout == 5.0


def test_env_nested_http_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nested http settings are overridable via APP_HTTP__ env vars."""
    monkeypatch.setenv("APP_HTTP__BASE_URL", "http://env.example.test")
    settings = FrameworkSettings()
    assert settings.http.base_url == "http://env.example.test"


def test_get_settings_caches() -> None:
    """get_settings returns the same cached instance."""
    first = get_settings()
    second = get_settings()
    assert first is second


def test_reset_settings_rebuilds() -> None:
    """reset_settings forces a fresh instance on next get_settings."""
    first = get_settings()
    reset_settings()
    second = get_settings()
    assert first is not second


def test_yaml_source_call_returns_mapping(tmp_path: Path) -> None:
    """The YAML source __call__ returns only fields present in the file."""
    _write_yaml(tmp_path, "dev", "env: dev\ndebug: true\n")
    source = YamlEnvSettingsSource(FrameworkSettings)
    assert source() == {"env": "dev", "debug": True}
