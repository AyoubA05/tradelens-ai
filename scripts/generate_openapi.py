"""Write the OpenAPI schema to a file for TypeScript codegen.

The running service does not serve /openapi.json in production, so the schema
is produced here instead. Generating it in CI and committing the result means a
backend change that breaks the frontend contract fails the build rather than
failing in a browser.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.tradelens.api.app import create_app  # noqa: E402

DEST = pathlib.Path("web/lib/api/openapi.json")


def main() -> None:
    if sys.version_info < (3, 10):
        # A version marker gives 3.9 an older FastAPI whose built-in schemas
        # differ; regenerating there would silently revert the contract that
        # production (python:3.11) actually serves.
        raise SystemExit(
            "generate_openapi.py must run on Python >= 3.10 (production runs 3.11)"
        )
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if args.stdout:
        sys.stdout.write(schema)
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(schema)
    print(f"wrote {DEST}")


if __name__ == "__main__":
    main()
