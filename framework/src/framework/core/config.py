"""Application configuration: multi-environment YAML + env override.

Configuration resolution order (highest priority first):

1. Init kwargs passed to ``FrameworkSettings(...)``.
2. Environment variables prefixed with ``APP_`` (nested via ``__``).
3. Values from a ``.env`` file (if present).
4. File-based secrets (reserved, currently unused).
5. Environment-specific YAML file at ``config/envs/<APP_ENV>.yaml``.
6. Field defaults declared on the model.

The active environment is selected by the ``APP_ENV`` environment variable
(default ``dev``). The YAML directory can be redirected via ``APP_CONFIG_DIR``
for tests and CI. Nested settings (e.g. ``http.base_url``) are overridable via
``APP_HTTP__BASE_URL``.
"""

from __future__ import annotations

import enum
import os
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from framework.core.exceptions import ConfigError

#: Default HTTP header used to propagate the trace id to downstream services.
DEFAULT_TRACE_HEADER: str = "X-Trace-Id"

__all__ = [
    "DEFAULT_TRACE_HEADER",
    "AISettings",
    "AppEnv",
    "AppSettings",
    "DatabaseSettings",
    "DatabaseType",
    "FrameworkSettings",
    "HttpSettings",
    "KafkaSettings",
    "MQSettings",
    "MQType",
    "NotificationSettings",
    "RabbitMQSettings",
    "RedisSettings",
    "RocketMQSettings",
    "WebSettings",
    "YamlEnvSettingsSource",
    "get_settings",
    "reset_settings",
]


class AppEnv(enum.Enum):
    """Supported deployment environments."""

    DEV = "dev"
    TEST = "test"
    UAT = "uat"
    PROD = "prod"

    @classmethod
    def from_string(cls, value: str) -> AppEnv:
        """Parse a (case-insensitive) environment name into an :class:`AppEnv`.

        Args:
            value: Environment name, e.g. ``"dev"``, ``"PROD"``.

        Returns:
            The matching :class:`AppEnv` member.

        Raises:
            ConfigError: If ``value`` is not a known environment.
        """
        if not isinstance(value, str):
            raise ConfigError(
                "APP_ENV must be a string",
                context={"value": repr(value), "valid": [e.value for e in cls]},
            )
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ConfigError(
            f"Unknown APP_ENV: {value!r}",
            context={"value": value, "valid": [e.value for e in cls]},
        )


def _config_dir() -> Path:
    """Resolve the directory holding per-environment YAML files.

    Honors ``APP_CONFIG_DIR``; defaults to ``config/envs`` relative to CWD.
    """
    override = os.environ.get("APP_CONFIG_DIR")
    if override:
        return Path(override)
    return Path("config/envs")


def _active_env() -> AppEnv:
    """Resolve the active environment from the ``APP_ENV`` env var.

    Defaults to :attr:`AppEnv.DEV` when unset or empty.
    """
    raw = os.environ.get("APP_ENV")
    if raw is None or raw == "":
        return AppEnv.DEV
    return AppEnv.from_string(raw)


class YamlEnvSettingsSource(PydanticBaseSettingsSource):
    """Pydantic settings source backed by an environment-specific YAML file.

    The file is selected as ``<config_dir>/<active_env>.yaml``. A missing
    file contributes nothing (defaults/other sources apply). A file whose
    top-level node is not a YAML mapping raises :class:`ConfigError`.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load()

    @staticmethod
    def _load() -> dict[str, Any]:
        """Load and validate the active environment's YAML file."""
        env = _active_env()
        path = _config_dir() / f"{env.value}.yaml"
        if not path.is_file():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError(
                "YAML config top-level must be a mapping",
                context={"path": str(path), "type": type(loaded).__name__},
            )
        return loaded

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Return ``(value, key, is_complex)`` for a model field from YAML.

        YAML yields native Python types (including nested mappings), so
        ``is_complex`` is always ``False``; pydantic coerces values (including
        nested model dicts) during final model validation.
        """
        value = self._data.get(field_name)
        return value, field_name, False

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:
        """Decode a complex field value, passing through native YAML types.

        YAML already yields dicts/lists/scalars, so only ``str`` values
        are JSON-decoded (mirroring the base behavior for env vars).
        """
        if isinstance(value, dict | list):
            return value
        return super().decode_complex_value(field_name, field, value)

    def __call__(self) -> dict[str, Any]:
        """Return YAML-provided values keyed by field name (None skipped)."""
        data: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, is_complex = self.get_field_value(field, field_name)
            prepared = self.prepare_field_value(
                field_name, field, value, value_is_complex=is_complex
            )
            if prepared is not None:
                data[key] = prepared
        return data


class HttpSettings(BaseModel):
    """HTTP client settings (nested under ``FrameworkSettings.http``).

    Overridable per environment via YAML (``http: {base_url: ...}``) or via
    env vars using the ``APP_HTTP__`` prefix (e.g. ``APP_HTTP__BASE_URL``).
    """

    base_url: str = ""
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    pool_timeout: float = 5.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    retry_max_attempts: int = 3
    retry_backoff_factor: float = 0.5
    retry_max_backoff: float = 30.0
    retry_statuses: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])
    retry_methods: list[str] = Field(
        default_factory=lambda: ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"]
    )
    raise_for_status: bool = False
    log_bodies: bool = False
    log_body_max_length: int = 1024
    sensitive_headers: list[str] = Field(default_factory=list)
    propagate_trace_id: bool = True
    trace_header: str = DEFAULT_TRACE_HEADER


class DatabaseType(enum.StrEnum):
    """Supported database backends (core-level config enum).

    Driver mapping and URL building live in ``framework.clients.db.dialects``
    so the core config module does not depend on a client layer (rule 11).
    """

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    ORACLE = "oracle"
    CLICKHOUSE = "clickhouse"


class DatabaseSettings(BaseModel):
    """Database client settings (nested under ``FrameworkSettings.database``).

    Credentials (``password``) must be supplied via env vars (``APP_DATABASE__PASSWORD``)
    or a ``.env`` file, never hardcoded in YAML. When ``url`` is set it takes
    precedence over the component fields (host/port/username/password/database).
    """

    type: DatabaseType = DatabaseType.POSTGRESQL
    host: str = "localhost"
    port: int | None = None
    username: str = ""
    password: str = ""
    database: str = ""
    url: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: float = 3600.0
    pool_pre_ping: bool = True
    echo: bool = False
    query_timeout: float | None = None
    connect_args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> Any:
        """Coerce string type values to :class:`DatabaseType` (case-insensitive)."""
        if isinstance(value, DatabaseType):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            try:
                return DatabaseType(normalized)
            except ValueError:
                raise ConfigError(
                    f"Unknown database type: {value!r}",
                    context={"value": value, "valid": [t.value for t in DatabaseType]},
                ) from None
        return value


class RedisSettings(BaseModel):
    """Redis cache client settings (nested under ``FrameworkSettings.redis``).

    Credentials (``password``) must be supplied via env vars
    (``APP_REDIS__PASSWORD``) or a ``.env`` file, never hardcoded in YAML.
    When ``url`` is set it takes precedence over component fields.
    """

    url: str = ""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    username: str = ""
    password: str = ""
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    health_check_interval: int = 30
    decode_responses: bool = True
    key_prefix: str = ""


class MQType(enum.StrEnum):
    """Supported message-queue backends (core-level config enum).

    Implementation mapping lives in ``framework.clients.mq`` so the core
    config module does not depend on a client layer (rule 11). New backends
    (RocketMQ, etc.) are added here first, then implemented in the client.
    """

    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"
    ROCKETMQ = "rocketmq"


class KafkaSettings(BaseModel):
    """Kafka-specific settings (nested under ``FrameworkSettings.mq.kafka``).

    All broker endpoints, credentials, and tuning knobs for the aiokafka
    producer/consumer. Secrets (``sasl_password``) must be supplied via env
    vars (``APP_MQ__KAFKA__SASL_PASSWORD``) or ``.env``, never in YAML.
    """

    bootstrap_servers: list[str] = Field(default_factory=lambda: ["localhost:9092"])
    client_id: str = "automation-platform"
    group_id: str = "automation-platform"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str = ""
    sasl_username: str = ""
    sasl_password: str = ""
    ssl_ca_location: str = ""
    auto_offset_reset: str = "latest"
    enable_auto_commit: bool = True
    auto_commit_interval_ms: int = 5000
    request_timeout_ms: int = 30000
    api_version: str = "auto"
    producer_acks: str = "1"
    producer_linger_ms: int = 0
    producer_compression: str = "none"
    consumer_fetch_min_bytes: int = 1
    consumer_fetch_max_wait_ms: int = 500


class RabbitMQSettings(BaseModel):
    """RabbitMQ-specific settings (nested under ``FrameworkSettings.mq.rabbitmq``).

    All broker endpoints, credentials, and tuning knobs for the aio-pika
    async client. Secrets (``password``) must be supplied via env vars
    (``APP_MQ__RABBITMQ__PASSWORD``) or ``.env``, never in YAML.
    """

    url: str = "amqp://guest:guest@localhost:5672/"
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = ""
    virtual_host: str = "/"
    exchange: str = ""
    exchange_type: str = "direct"
    exchange_durable: bool = True
    queue_durable: bool = True
    queue_auto_delete: bool = False
    message_delivery_mode: int = 2
    prefetch_count: int = 10
    connection_timeout: float = 10.0
    heartbeat: int = 60
    publisher_confirms: bool = True


class RocketMQSettings(BaseModel):
    """RocketMQ-specific settings (nested under ``FrameworkSettings.mq.rocketmq``).

    All broker endpoints, credentials, and tuning knobs for the RocketMQ
    producer/consumer. Secrets (``access_key``/``secret_key``) must be
    supplied via env vars (``APP_MQ__ROCKETMQ__SECRET_KEY``) or ``.env``,
    never in YAML.
    """

    name_server: str = "localhost:9876"
    group_name: str = "automation-platform"
    client_id: str = "automation-platform"
    instance_name: str = "automation-platform"
    access_key: str = ""
    secret_key: str = ""
    access_channel: str = ""
    namespace: str = ""
    send_msg_timeout_ms: int = 30000
    producer_retry_times: int = 3
    producer_compress_msg_body_threshold: int = 4096
    consumer_thread_count: int = 20
    consumer_message_batch_max_size: int = 32
    consumer_max_reconsume_times: int = 16
    consumer_consume_timeout_ms: int = 300000
    consumer_consume_from_where: str = "CONSUME_FROM_LAST_OFFSET"
    message_max_body_size: int = 4 * 1024 * 1024


class MQSettings(BaseModel):
    """Message-queue client settings (nested under ``FrameworkSettings.mq``).

    The ``type`` field selects the broker backend. ``kafka``,
    ``rocketmq``, and ``rabbitmq`` are all implemented.
    """

    type: MQType = MQType.KAFKA
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    rocketmq: RocketMQSettings = Field(default_factory=RocketMQSettings)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> Any:
        """Coerce string type values to :class:`MQType` (case-insensitive)."""
        if isinstance(value, MQType):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            try:
                return MQType(normalized)
            except ValueError:
                raise ConfigError(
                    f"Unknown MQ type: {value!r}",
                    context={"value": value, "valid": [t.value for t in MQType]},
                ) from None
        return value


class AISettings(BaseModel):
    """AI / LLM settings (nested under ``FrameworkSettings.ai``).

    Configuration for the LLM-powered failure analyzer. The API key must be
    supplied via env vars (``APP_AI__API_KEY``) or ``.env``, never in YAML
    (rule 10). Supports any OpenAI-compatible endpoint (OpenAI, Azure,
    Ollama, vLLM, etc.).
    """

    enabled: bool = False
    provider: str = "openai"
    api_url: str = "https://api.openai.com/v1/chat/completions"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 1024
    timeout_s: float = 30.0
    max_exchanges_in_prompt: int = 5
    system_prompt: str = (
        "You are a test failure analyzer. Given a test failure context "
        "(test name, error, traceback, HTTP exchanges), identify the root "
        "cause and suggest a fix. Respond in JSON with keys: root_cause, "
        "suggestion, confidence (0.0-1.0), category."
    )


class AppSettings(BaseModel):
    """App automation settings (nested under ``FrameworkSettings.app``).

    Appium server and capabilities configuration. Secrets (``app_password``)
    must be supplied via env vars or ``.env``, never in YAML.
    """

    server_url: str = "http://localhost:4723"
    platform_name: str = "Android"
    automation_name: str = "UiAutomator2"
    device_name: str = ""
    app_package: str = ""
    app_activity: str = ""
    app_path: str = ""
    no_reset: bool = True
    full_reset: bool = False
    new_command_timeout: int = 300
    screenshot_on_failure: bool = True
    implicit_wait_ms: int = 5000
    udid: str = ""
    platform_version: str = ""


class WebSettings(BaseModel):
    """Web automation settings (nested under ``FrameworkSettings.web``).

    Playwright browser configuration. Secrets (``http_password``) must be
    supplied via env vars or ``.env``, never in YAML.
    """

    browser: str = "chromium"
    headless: bool = True
    base_url: str = ""
    timeout_ms: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    screenshot_on_failure: bool = True
    http_username: str = ""
    http_password: str = ""
    slow_mo_ms: int = 0
    ignore_https_errors: bool = False
    channel: str = ""
    #: Browser channel to use the system-installed browser (e.g. "chrome",
    #: "msedge") instead of the Playwright-bundled binary. Empty = bundled.


class NotificationSettings(BaseModel):
    """Email notification settings (nested under FrameworkSettings.notification).

    Credentials (``smtp_password``) must be supplied via env vars
    (``APP_NOTIFICATION__SMTP_PASSWORD``), never hardcoded (rule 10).
    """

    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    use_tls: bool = True
    from_addr: str = ""
    to_addrs: list[str] = []
    subject_prefix: str = "[Automation]"


class FrameworkSettings(BaseSettings):
    """Top-level framework settings, multi-environment aware.

    Environment variables use the ``APP_`` prefix (e.g. ``APP_LOG_LEVEL``);
    ``APP_ENV`` selects both the active environment and its YAML file. Nested
    settings are overridable via ``__`` (e.g. ``APP_HTTP__BASE_URL``).
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    name: str = "automation-platform"
    env: AppEnv = AppEnv.DEV
    debug: bool = False
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    log_rotation: str = "00:00"
    log_retention: str = "14 days"
    http: HttpSettings = Field(default_factory=HttpSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    mq: MQSettings = Field(default_factory=MQSettings)
    ai: AISettings = Field(default_factory=AISettings)
    app: AppSettings = Field(default_factory=AppSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)

    @field_validator("env", mode="before")
    @classmethod
    def _normalize_env(cls, value: Any) -> Any:
        """Coerce string env/yaml values to :class:`AppEnv` (case-insensitive)."""
        if isinstance(value, AppEnv):
            return value
        if isinstance(value, str):
            return AppEnv.from_string(value)
        return value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order sources high->low: init, env, dotenv, secrets, YAML, defaults."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            YamlEnvSettingsSource(settings_cls),
        )


_settings_lock = threading.Lock()
_settings: FrameworkSettings | None = None


def get_settings() -> FrameworkSettings:
    """Return the process-wide cached :class:`FrameworkSettings`.

    Lazily constructed on first access and guarded by a lock for thread
    safety. Call :func:`reset_settings` to force re-evaluation (e.g. after
    changing environment variables in tests).
    """
    global _settings
    if _settings is not None:
        return _settings
    with _settings_lock:
        if _settings is None:
            _settings = FrameworkSettings()
        return _settings


def reset_settings() -> None:
    """Clear the cached settings so the next :func:`get_settings` rebuilds."""
    global _settings
    with _settings_lock:
        _settings = None
