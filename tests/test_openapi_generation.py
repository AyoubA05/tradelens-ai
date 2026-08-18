import json
import pathlib
import subprocess
import sys


def test_the_committed_schema_matches_the_application():
    """Drift here means the TypeScript types describe an API that no longer
    exists — and the compiler would keep saying everything is fine."""
    generated = subprocess.run(
        [sys.executable, "scripts/generate_openapi.py", "--stdout"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    committed = pathlib.Path("web/lib/api/openapi.json").read_text()
    assert json.loads(generated) == json.loads(committed), (
        "run: python scripts/generate_openapi.py && cd web && npm run api:types"
    )


def test_the_schema_documents_the_whoami_endpoint():
    schema = json.loads(pathlib.Path("web/lib/api/openapi.json").read_text())
    assert "/v1/session/whoami" in schema["paths"]
