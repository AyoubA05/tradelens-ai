"""The production preflight reports duplicates, blocks, and changes nothing."""

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def _db(tmp_path, rows):
    url = f"sqlite:///{tmp_path / 'preflight.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE weekly_reviews (id INTEGER PRIMARY KEY, user_id INTEGER, "
                "week_start VARCHAR NOT NULL, content_md TEXT)"
            )
        )
        for user_id, week in rows:
            conn.execute(
                text(
                    "INSERT INTO weekly_reviews (user_id, week_start, content_md) "
                    "VALUES (:u, :w, 'private recap text')"
                ),
                {"u": user_id, "w": week},
            )
    engine.dispose()
    return url


def _run(url):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "scripts/preflight_weekly_unique.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _count(url):
    engine = create_engine(url)
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM weekly_reviews")).scalar()
    engine.dispose()
    return n


def test_no_duplicates_allows_deployment(tmp_path):
    url = _db(tmp_path, [(1, "2026-09-07"), (1, "2026-09-14"), (None, "2026-09-07")])
    result = _run(url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 duplicate" in result.stdout


def test_duplicates_block_deployment_and_are_reported_without_content(tmp_path):
    url = _db(
        tmp_path,
        [
            (1, "2026-09-07"),
            (1, "2026-09-07"),
            (2, "2026-09-14"),
            (2, "2026-09-14"),
            (2, "2026-09-14"),
            (None, "2026-09-07"),
            (None, "2026-09-07"),  # ownerless legacy rows never collide
        ],
    )
    result = _run(url)
    assert result.returncode == 3
    assert "2 duplicate" in result.stdout and "STOP" in result.stdout
    assert "user_id=1 week_start=2026-09-07 rows=2" in result.stdout
    assert "user_id=2 week_start=2026-09-14 rows=3" in result.stdout
    assert "private recap text" not in result.stdout + result.stderr
    assert _count(url) == 7  # nothing deleted or merged


def test_a_missing_url_or_table_is_an_error_not_a_pass(tmp_path):
    no_url = subprocess.run(
        [sys.executable, "scripts/preflight_weekly_unique.py"],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k != "DATABASE_URL"},
        capture_output=True,
        text=True,
    )
    assert no_url.returncode == 2
    empty = _run(f"sqlite:///{tmp_path / 'empty.db'}")
    assert empty.returncode == 2
    assert str(tmp_path) not in empty.stdout + empty.stderr  # URL never printed
