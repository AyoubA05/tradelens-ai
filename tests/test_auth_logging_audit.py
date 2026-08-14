"""No auth code path may log a reusable secret.

This is a source audit rather than a runtime one on purpose. A runtime test
proves that the paths it happens to exercise stay quiet; it says nothing about
the exception handler nobody triggered. Reading the source catches the branch
that only runs when the database is down — which is exactly the branch someone
adds a debug print to at 2am and forgets.

What logging is *allowed* to carry is deliberately narrow: an event name, a
reason, a timestamp, a rate-limit bucket, and counts. Anything that could be
replayed — a password, a hash, a verification/reset/handoff/session token, a
cookie, a connection string, or a URL containing any of those — must not reach
a log line, an exception message, or an HTTP response.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PY_AUTH_FILES = [
    "src/tradelens/services/auth_sessions.py",
    "src/tradelens/services/auth_handoff.py",
    "src/tradelens/services/auth_exchange.py",
    "src/tradelens/services/password_reset.py",
    "src/tradelens/services/users.py",
    "src/tradelens/ui/components/site_auth.py",
    "src/tradelens/ui/components/auth.py",
    "src/tradelens/ui/components/strategy_gate.py",
    "src/tradelens/settings_source.py",
]

TS_AUTH_DIRS = ["web/lib/auth", "web/lib/security", "web/lib/mail", "web/app/api/auth"]

# Names whose *value* is a reusable secret. Matched as whole identifiers so
# `token_hash` (a stored digest, safe to count) is not confused with `token`.
SECRET_IDENTIFIERS = [
    "password",
    "raw_password",
    "new_password",
    "password_hash",
    "passwordHash",
    "token",
    "raw_ht",
    "raw_token",
    "session_token",
    "sessionToken",
    "cookie",
    "DATABASE_URL",
    "database_url",
]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Strip comments and docstring-ish lines.

    Every one of these files explains in prose *why* it does not log a token,
    and a naive substring scan flags that prose as the violation it warns
    against. This has produced a false failure twice; the stripping is the fix.
    """
    out = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(('"""', "'''")):
            # Toggle unless the docstring opens and closes on one line.
            if not (len(stripped) > 3 and stripped.endswith(('"""', "'''"))):
                in_block = not in_block
            continue
        if in_block:
            continue
        if stripped.startswith(("#", "//", "*", "/*")):
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", PY_AUTH_FILES)
def test_python_logging_calls_carry_no_secret(relative):
    """Walk the AST and inspect the arguments of every logging call."""
    tree = ast.parse(source(relative))
    offenders = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id if isinstance(func, ast.Name) else ""
        )
        if name not in {
            "debug",
            "info",
            "warning",
            "error",
            "exception",
            "critical",
            "print",
        }:
            continue

        for argument in list(node.args) + [kw.value for kw in node.keywords]:
            for inner in ast.walk(argument):
                if isinstance(inner, ast.Name) and inner.id in SECRET_IDENTIFIERS:
                    offenders.append(f"{relative}: logs `{inner.id}`")
                if (
                    isinstance(inner, ast.Attribute)
                    and inner.attr in SECRET_IDENTIFIERS
                ):
                    offenders.append(f"{relative}: logs `.{inner.attr}`")

    assert offenders == [], offenders


@pytest.mark.parametrize("relative", PY_AUTH_FILES)
def test_python_never_logs_the_url_or_query_params(relative):
    """A URL is a credential here: the Streamlit bearer rides in one."""
    code = code_only(source(relative))
    for forbidden in (
        "st.query_params)",
        "log.info(st.query_params",
        "print(st.query_params",
    ):
        assert forbidden not in code, f"{relative} logs the URL"


def test_database_errors_reduce_to_a_type_name():
    """A DSN carries a password, and SQLAlchemy inlines the URL in its message."""
    code = source("src/tradelens/db/session.py")
    assert "return type(exc).__name__" in code
    body = code_only(code)
    assert "str(exc)" not in body
    assert "{exc}" not in body


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


def ts_files():
    for directory in TS_AUTH_DIRS:
        for path in sorted((ROOT / directory).rglob("*.ts")):
            yield path


CONSOLE = re.compile(r"console\.(log|info|warn|error|debug)\s*\(([^;]*)\)", re.DOTALL)


def test_typescript_console_calls_carry_no_secret():
    offenders = []
    for path in ts_files():
        code = code_only(path.read_text(encoding="utf-8"))
        for match in CONSOLE.finditer(code):
            arguments = match.group(2)
            for identifier in SECRET_IDENTIFIERS:
                if re.search(rf"\b{re.escape(identifier)}\b", arguments):
                    offenders.append(
                        f"{path.relative_to(ROOT)}: console logs `{identifier}`"
                    )
    assert offenders == [], offenders


def test_typescript_never_logs_a_whole_request_or_headers():
    """`console.log(request)` prints the cookie header with the session in it."""
    offenders = []
    for path in ts_files():
        code = code_only(path.read_text(encoding="utf-8"))
        for match in CONSOLE.finditer(code):
            arguments = match.group(2)
            if re.search(r"\b(request|req|headers|body|payload)\b", arguments):
                offenders.append(
                    f"{path.relative_to(ROOT)}: console logs a request object"
                )
    assert offenders == [], offenders


def test_the_shared_logger_drops_sensitive_keys_rather_than_redacting():
    """A `[redacted]` marker still tells a reader the field was present."""
    code = source("web/lib/security/responses.ts")
    assert "NEVER_LOG" in code
    assert "continue;" in code  # the key is skipped, not rewritten
    for name in ("password", "token", "handoff", "session", "DATABASE_URL"):
        assert f'"{name}"' in code, name


def test_no_auth_route_returns_a_raw_error_to_the_client():
    """Driver text can carry the DSN; a stack can carry the token."""
    offenders = []
    for path in (ROOT / "web/app/api/auth").rglob("*.ts"):
        code = code_only(path.read_text(encoding="utf-8"))
        for pattern in (
            r"error:\s*String\(",
            r"error:\s*\w+\.message",
            r"error:\s*err\b",
        ):
            if re.search(pattern, code):
                offenders.append(f"{path.relative_to(ROOT)}: returns a raw error")
    assert offenders == [], offenders
