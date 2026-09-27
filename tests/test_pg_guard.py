"""The live-Postgres identity guard refuses before it connects anywhere."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pg_guard import NotTheDisposableDatabase, require_disposable_database  # noqa: E402

URL = "postgresql://u:p@ep-disposable.example.test/neondb?sslmode=require"


@pytest.fixture
def no_connect(monkeypatch):
    import sqlalchemy

    def refuse(*_a, **_k):
        raise AssertionError("the guard connected before checking identity")

    monkeypatch.setattr(sqlalchemy, "create_engine", refuse)


def test_refuses_without_an_expected_host(monkeypatch, no_connect):
    monkeypatch.delenv("TRADELENS_PG_EXPECT_HOST", raising=False)
    with pytest.raises(NotTheDisposableDatabase):
        require_disposable_database(URL)


def test_refuses_a_different_host(monkeypatch, no_connect):
    monkeypatch.setenv("TRADELENS_PG_EXPECT_HOST", "ep-disposable.example.test")
    with pytest.raises(NotTheDisposableDatabase):
        require_disposable_database(URL.replace("ep-disposable", "ep-production"))


def test_refuses_a_host_that_merely_contains_the_expected_one(monkeypatch, no_connect):
    monkeypatch.setenv("TRADELENS_PG_EXPECT_HOST", "ep-disposable.example.test")
    with pytest.raises(NotTheDisposableDatabase):
        require_disposable_database(
            URL.replace(
                "ep-disposable.example.test", "ep-disposable.example.test.evil.io"
            )
        )


def test_the_refusal_never_echoes_the_url(monkeypatch, no_connect):
    monkeypatch.setenv("TRADELENS_PG_EXPECT_HOST", "elsewhere")
    with pytest.raises(NotTheDisposableDatabase) as caught:
        require_disposable_database(URL)
    assert "u:p@" not in str(caught.value) and "ep-disposable" not in str(caught.value)
