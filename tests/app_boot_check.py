"""
Subprocess helper: boot a Streamlit page under AppTest with an ISOLATED DB.

Run in a child process (not collected by pytest — no test_ prefix) so module
state and the DATABASE_URL engine are fully isolated from the parent suite. This
realizes "env var before import": DATABASE_URL is set in the child's environment
before any src.tradelens module is imported, so the engine binds to the tmp DB
with no post-import SessionLocal monkeypatching.

⚠️  DO NOT "optimize" this back into an in-process pytest fixture (e.g. setting
DATABASE_URL then purging src.tradelens.* from sys.modules and re-importing).
That is a known Streamlit-testing trap: reloading the package mid-suite creates a
SECOND copy of ai_client, so every downstream `isinstance(x, AIUnavailable)`
check in other test files (which bound those symbols at collection time) fails.
We measured 34–47 spurious failures doing exactly that. A subprocess is the
correct, suite-safe isolation boundary. Keep it.

Usage:
    DATABASE_URL=sqlite:///<tmp> python app_boot_check.py <root> <app> <marker> <0|1>

Exits 0 on success; nonzero with a message on failure.
"""

import sys


def main() -> int:
    root, app_path, marker, seed = sys.argv[1:5]
    sys.path.insert(0, root)

    from src.tradelens.db.init_db import init_db

    init_db()

    if seed == "1":
        from src.tradelens.db.models import Trade
        from src.tradelens.db.session import SessionLocal

        s = SessionLocal()
        s.add_all(
            [
                Trade(
                    trade_date="2026-06-15",
                    asset="NQ",
                    direction="Long",
                    result="Win",
                    pnl=200.0,
                    ai_grade="A",
                    killzone="ny_am",
                ),
                Trade(
                    trade_date="2026-06-16",
                    asset="ES",
                    direction="Short",
                    result="Loss",
                    pnl=-90.0,
                    ai_grade="C",
                    killzone="london",
                ),
            ]
        )
        s.commit()
        s.close()

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(app_path).run()
    if at.exception:
        print(f"app raised: {at.exception}", file=sys.stderr)
        return 2

    # marker == "-" means boot-only: assert no exception, skip the content check.
    if marker != "-":
        markdowns = [m.value for m in at.markdown]
        if not any(marker in v for v in markdowns):
            print(f"marker not found: {marker}", file=sys.stderr)
            return 3

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
