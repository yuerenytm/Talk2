from __future__ import annotations

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "Talk2"
ACCOUNT = "api_key"

_memory_key: str | None = None


def get_api_key() -> str:
    global _memory_key
    if _memory_key:
        return _memory_key
    try:
        return keyring.get_password(SERVICE, ACCOUNT) or ""
    except KeyringError:
        return _memory_key or ""


def set_api_key(value: str, persist: bool = True) -> str:
    """Store API key. Returns 'keyring' or 'memory'."""
    global _memory_key
    value = (value or "").strip()
    if persist:
        try:
            if value:
                keyring.set_password(SERVICE, ACCOUNT, value)
            else:
                try:
                    keyring.delete_password(SERVICE, ACCOUNT)
                except PasswordDeleteError:
                    pass
            _memory_key = None
            return "keyring"
        except KeyringError:
            _memory_key = value
            return "memory"
    _memory_key = value
    return "memory"
