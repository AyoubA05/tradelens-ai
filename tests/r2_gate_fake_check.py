"""Subprocess helper: run scripts/gate_r2_verify.py's checks against an
in-memory fake of R2 (S3 API + HTTP), in a throwaway SQLite database.

Usage: python r2_gate_fake_check.py <variant>   -> prints JSON results.
Not collected by pytest.
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/r2fake.db"
os.environ.update(
    R2_ACCOUNT_ID="a",
    R2_ACCESS_KEY_ID="k",
    R2_SECRET_ACCESS_KEY="s",
    R2_BUCKET="gate-test",
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gate_r2_verify as gate  # noqa: E402
from src.tradelens.api import storage  # noqa: E402

VARIANT = sys.argv[1]
SITE = "https://staging.example.test"


class Missing(Exception):
    response = {
        "Error": {"Code": "NoSuchKey"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.lifecycle = [
            {
                "Status": "Enabled",
                "Filter": {"Prefix": "quarantine/"},
                "Expiration": {"Days": 1},
            }
        ]
        self.cors = [
            {
                "AllowedOrigins": [SITE],
                "AllowedMethods": ["PUT", "GET"],
                "AllowedHeaders": ["content-type"],
            }
        ]
        if VARIANT == "no-lifecycle":
            self.lifecycle = None
        if VARIANT == "bucket-wide-expiry":
            self.lifecycle.append(
                {
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "Expiration": {"Days": 30},
                }
            )
        if VARIANT == "wildcard-cors":
            self.cors[0]["AllowedOrigins"] = ["*"]

    def generate_presigned_url(self, method, Params, ExpiresIn):
        return f"fake://{method}?key={Params['Key']}&ct={Params.get('ContentType', '')}"

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Missing()
        body, ctype = self.objects[Key]
        return {
            "Body": io.BytesIO(body),
            "ContentLength": len(body),
            "ContentType": ctype,
        }

    def put_object(self, Bucket, Key, Body, ContentType=None, **_):
        self.objects[Key] = (
            Body if isinstance(Body, bytes) else Body.read(),
            ContentType,
        )

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def list_objects_v2(self, Bucket, Prefix, **_):
        return {
            "Contents": [
                {"Key": k} for k in sorted(self.objects) if k.startswith(Prefix)
            ],
            "IsTruncated": False,
        }

    def get_bucket_lifecycle_configuration(self, Bucket):
        if self.lifecycle is None:
            raise Missing()
        return {"Rules": self.lifecycle}

    def get_bucket_cors(self, Bucket):
        return {"CORSRules": self.cors}


R2 = FakeR2()


def fake_http(method, url, *, body=b"", headers=None):
    headers = headers or {}
    parsed = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    key = q["key"]
    if method == "OPTIONS":
        origin = headers.get("Origin")
        allowed = any(
            origin in r["AllowedOrigins"] or "*" in r["AllowedOrigins"] for r in R2.cors
        )
        return (
            (200, {"access-control-allow-origin": origin} if allowed else {}, b"")
            if allowed
            else (403, {}, b"")
        )
    if method == "PUT":
        if (
            headers.get("Content-Type") != q.get("ct")
            and VARIANT != "unsigned-content-type"
        ):
            return 403, {}, b""
        R2.objects[key] = (body, headers.get("Content-Type"))
        return 200, {}, b""
    if method == "GET":
        if key not in R2.objects:
            return 404, {}, b""
        return 200, {}, R2.objects[key][0]
    return 405, {}, b""


storage._client = lambda: R2
gate._seed_owners()
run = gate.Run(storage, R2, "gate-test", SITE, 7, http_fn=fake_http)
results = run.all()
print(json.dumps({r["check"]: r["result"] for r in results}))
