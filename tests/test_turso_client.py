from __future__ import annotations

import pytest


def test_turso_active_false_without_env(monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TURSO_ACTIVE", raising=False)

    from db._base import turso_active, turso_configured

    assert not turso_configured()
    assert not turso_active()


def test_turso_configured_but_inactive_by_default(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.delenv("TURSO_ACTIVE", raising=False)

    from importlib import reload

    import db._base as base

    reload(base)
    assert base.turso_configured()
    assert not base.turso_active()


def test_storage_backend_stays_postgres_with_turso_standby(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token")

    from importlib import reload

    import db._base as base

    reload(base)
    assert base.storage_backend_name() == "postgres"