"""jmseg API 客户端."""

from api.base import AuthKind, AuthScheme, BaseClient, EndpointSpec, SyncClient, detect_auth_scheme
from api.station_quote import StationQuoteClient

__all__ = [
    "AuthKind",
    "AuthScheme",
    "BaseClient",
    "EndpointSpec",
    "StationQuoteClient",
    "SyncClient",
    "detect_auth_scheme",
]
