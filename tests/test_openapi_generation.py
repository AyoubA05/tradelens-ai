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
    assert json.loads(generated) == json.loads(
        committed
    ), "run: python scripts/generate_openapi.py && cd web && npm run api:types"


def test_the_schema_documents_the_whoami_endpoint():
    schema = json.loads(pathlib.Path("web/lib/api/openapi.json").read_text())
    assert "/v1/session/whoami" in schema["paths"]


def test_whoami_has_a_concrete_generated_response_contract():
    schema = json.loads(pathlib.Path("web/lib/api/openapi.json").read_text())
    response = schema["paths"]["/v1/session/whoami"]["get"]["responses"]["200"]
    response_schema = response["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/WhoAmI"}
    assert schema["components"]["schemas"]["WhoAmI"] == {
        "properties": {"user_id": {"title": "User Id", "type": "integer"}},
        "required": ["user_id"],
        "title": "WhoAmI",
        "type": "object",
    }
