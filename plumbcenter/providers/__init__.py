"""Qt-free AI provider catalog, secret storage, configuration, and connection tests."""

from .catalog import PROVIDERS, ProviderSpec, get_provider
from .secrets import (
    DpapiFileBackend,
    KeyringBackend,
    MemoryBackend,
    SecretBackend,
    default_backend,
)
from .store import ProviderConfig, ProviderError, ProviderStore, plumbnote_home
from .tester import TestResult, test_connection

__all__ = [
    "PROVIDERS",
    "ProviderSpec",
    "get_provider",
    "SecretBackend",
    "KeyringBackend",
    "DpapiFileBackend",
    "MemoryBackend",
    "default_backend",
    "ProviderConfig",
    "ProviderError",
    "ProviderStore",
    "plumbnote_home",
    "TestResult",
    "test_connection",
]
