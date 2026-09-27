"""Production gate 6 — live R2 verification with scoped test credentials.

Drives the application's own storage functions (`src/tradelens/api/storage.py`)
against a DEDICATED TEST bucket, as two synthetic owners that exist only in a
throwaway SQLite database. It never touches the application database and never
runs the legacy screenshot migration.

Refuses to start unless all of these hold:

* `TRADELENS_R2_GATE_ALLOW=1`;
* `R2_BUCKET` equals `TRADELENS_R2_EXPECT_BUCKET` (named twice, deliberately);
* `R2_BUCKET` differs from `TRADELENS_R2_PRODUCTION_BUCKET` when that is set;
* both synthetic owners' prefixes are empty before the run.

Checks (each PASS/FAIL with evidence): quarantine lifecycle rule; CORS
configuration and a live browser-style preflight (allowed and foreign origin);
attach -> finalize with normalisation to PNG; owner-only download; cross-owner
finalize/abandon refused; abandon removes the quarantine object; a non-image is
rejected and discarded; the signed Content-Type is enforced by R2; trade
deletion is owner-scoped. Everything the run created is deleted at the end and
the prefixes are verified empty.

Expiry itself takes days, so it is a two-step probe:
    --plant-expiry-probe   leaves one quarantine object and prints its key
    --check-expiry-probe K later reports whether R2 expired it

Credentials come from the environment of whoever runs this; none is printed.

    R2_ACCOUNT_ID=… R2_ACCESS_KEY_ID=… R2_SECRET_ACCESS_KEY=… R2_BUCKET=<test> \\
    TRADELENS_R2_EXPECT_BUCKET=<test> TRADELENS_R2_GATE_ALLOW=1 \\
    SITE_ORIGIN=https://<staging origin> python scripts/gate_r2_verify.py --report r2.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

OWNER_A, OWNER_B = 990001, 990002
TRADE_A, TRADE_B = 880001, 880002
FOREIGN_ORIGIN = "https://gate-foreign-origin.invalid"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class Refused(RuntimeError):
    pass


# ── HTTP (injectable for the self-test) ───────────────────────────────────────


def http(method: str, url: str, *, body: bytes = b"", headers: dict | None = None):
    """(status, headers-dict-lowercased, body). Never raises for an HTTP status."""
    request = urllib.request.Request(
        url, data=body or None, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read(),
            )
    except urllib.error.HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


# ── fixtures ─────────────────────────────────────────────────────────────────


def _jpeg() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 60, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _seed_owners() -> None:
    from src.tradelens.db.init_db import init_db
    from src.tradelens.db.models import Trade, User
    from src.tradelens.db.session import SessionLocal

    init_db()
    db = SessionLocal()
    try:
        for uid, tid in ((OWNER_A, TRADE_A), (OWNER_B, TRADE_B)):
            db.add(User(id=uid, username=f"gate6-{uid}", password_hash="x"))
            db.flush()
            db.add(
                Trade(
                    id=tid,
                    user_id=uid,
                    trade_date="2026-09-07",
                    asset="NQ",
                    direction="Long",
                    result="Win",
                )
            )
        db.commit()
    finally:
        db.close()


def _record_screenshot(owner: int, trade: int, key: str) -> int:
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        del owner  # ownership is through the trade row
        row = Screenshot(trade_id=trade, file_path=key)
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


# ── the run ──────────────────────────────────────────────────────────────────


class Run:
    def __init__(self, storage, client, bucket, site_origin, max_days, http_fn=http):
        self.storage, self.client, self.bucket = storage, client, bucket
        self.site_origin, self.max_days, self.http = site_origin, max_days, http_fn
        self.results = []

    def check(self, name, ok, evidence):
        self.results.append(
            {"check": name, "result": "PASS" if ok else "FAIL", "evidence": evidence}
        )
        print(f"{'PASS' if ok else 'FAIL'}  {name} — {evidence}", flush=True)

    def keys(self, prefix):
        out, token = [], None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            out += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return out
            token = page.get("NextContinuationToken")

    def test_prefixes(self):
        return [
            p for o in (OWNER_A, OWNER_B) for p in (f"u/{o}/", f"quarantine/u/{o}/")
        ]

    def exists(self, key):
        return key in self.keys(key)

    def upload(self, owner, trade, content_type, body, *, put_type=None):
        ticket = self.storage.presign_upload(owner, trade, content_type)
        status, _, _ = self.http(
            "PUT",
            ticket["url"],
            body=body,
            headers={"Content-Type": put_type or content_type},
        )
        return ticket["key"], status

    def lifecycle(self):
        try:
            rules = self.client.get_bucket_lifecycle_configuration(
                Bucket=self.bucket
            ).get("Rules", [])
        except (
            Exception
        ) as exc:  # noqa: BLE001 — "no configuration" is itself the finding
            self.check(
                "quarantine lifecycle rule",
                False,
                f"no lifecycle configuration ({type(exc).__name__})",
            )
            return
        quarantine, dangerous = [], []
        for rule in rules:
            if rule.get("Status") != "Enabled" or not rule.get("Expiration"):
                continue
            prefix = (rule.get("Filter") or {}).get(
                "Prefix", rule.get("Prefix", "")
            ) or ""
            days = rule["Expiration"].get("Days")
            # Covers every quarantine key without reaching beyond "quarantine".
            if "quarantine/u/".startswith(prefix) and prefix.startswith("quarantine"):
                quarantine.append((prefix, days))
            # Would also expire promoted screenshots: traders' images.
            if "u/".startswith(prefix) or prefix.startswith("u/"):
                dangerous.append((prefix or "<whole bucket>", days))
        ok = (
            any(d is not None and d <= self.max_days for _, d in quarantine)
            and not dangerous
        )
        self.check(
            "quarantine lifecycle rule",
            ok,
            f"quarantine rules: {quarantine or 'none'} (need Days <= {self.max_days}); "
            f"rules that would expire final screenshots: {dangerous or 'none'}",
        )

    def cors(self):
        try:
            rules = self.client.get_bucket_cors(Bucket=self.bucket).get("CORSRules", [])
        except Exception as exc:  # noqa: BLE001
            self.check(
                "CORS configuration",
                False,
                f"no CORS configuration ({type(exc).__name__})",
            )
            return
        allowed = [
            r
            for r in rules
            if self.site_origin in r.get("AllowedOrigins", [])
            and "PUT" in r.get("AllowedMethods", [])
        ]
        wildcard = any("*" in r.get("AllowedOrigins", []) for r in rules)
        self.check(
            "CORS configuration",
            bool(allowed) and not wildcard,
            f"PUT allowed for {self.site_origin}: {bool(allowed)}; wildcard origin: {wildcard}",
        )
        ticket = self.storage.presign_upload(OWNER_A, TRADE_A, "image/png")
        results = {}
        for origin in (self.site_origin, FOREIGN_ORIGIN):
            status, headers, _ = self.http(
                "OPTIONS",
                ticket["url"],
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            results[origin] = (status, headers.get("access-control-allow-origin"))
        site_status, site_allow = results[self.site_origin]
        ok = (
            site_status < 300
            and site_allow == self.site_origin
            and results[FOREIGN_ORIGIN][1] is None
        )
        self.check(
            "CORS live preflight",
            ok,
            f"site origin -> {results[self.site_origin]}; foreign -> {results[FOREIGN_ORIGIN]}",
        )

    def attach_and_download(self):
        key, status = self.upload(OWNER_A, TRADE_A, "image/jpeg", _jpeg())
        if status >= 300:
            self.check("attach: presigned PUT", False, f"HTTP {status}")
            return None
        final = self.storage.finalize_upload(OWNER_A, TRADE_A, key)
        final_key = final["key"]
        obj = self.client.get_object(Bucket=self.bucket, Key=final_key)
        body = obj["Body"].read()
        ok = (
            final_key.startswith(f"u/{OWNER_A}/t/{TRADE_A}/")
            and final_key.endswith(".png")
            and body.startswith(PNG_MAGIC)
            and obj.get("ContentType") == "image/png"
            and not self.exists(key)
        )
        self.check(
            "attach -> finalize normalises JPEG to PNG under the owner prefix",
            ok,
            f"final key shape ok: {final_key.startswith(f'u/{OWNER_A}/t/{TRADE_A}/') and final_key.endswith('.png')}; "
            f"PNG bytes: {body.startswith(PNG_MAGIC)}; ContentType: {obj.get('ContentType')}; quarantine removed: {not self.exists(key)}",
        )
        sid = _record_screenshot(OWNER_A, TRADE_A, final_key)
        url_a = self.storage.presign_download(OWNER_A, sid)
        url_b = self.storage.presign_download(OWNER_B, sid)
        got = self.http("GET", url_a)[0] if url_a else None
        self.check(
            "download is owner-only",
            bool(url_a) and got == 200 and url_b is None,
            f"owner URL: {bool(url_a)} (GET {got}); other owner URL: {url_b is not None}",
        )
        return final_key

    def cross_owner_and_abandon(self):
        key, status = self.upload(OWNER_A, TRADE_A, "image/png", _png())
        refused = []
        for action in ("finalize_upload", "abandon_upload"):
            try:
                getattr(self.storage, action)(OWNER_B, TRADE_A, key)
                refused.append((action, False))
            except PermissionError:
                refused.append((action, True))
        still = self.exists(key)
        self.check(
            "other owner cannot finalize or abandon",
            status < 300 and all(r for _, r in refused) and still,
            f"refused: {refused}; object intact: {still}",
        )
        self.storage.abandon_upload(OWNER_A, TRADE_A, key)
        self.check(
            "abandon removes the quarantine object",
            not self.exists(key),
            f"present after abandon: {self.exists(key)}",
        )

    def rejection(self):
        key, status = self.upload(
            OWNER_A, TRADE_A, "image/png", b"this is not an image" * 50
        )
        try:
            self.storage.finalize_upload(OWNER_A, TRADE_A, key)
            outcome = "accepted"
        except self.storage.UploadRejected:
            outcome = "rejected"
        self.check(
            "non-image rejected and discarded",
            status < 300 and outcome == "rejected" and not self.exists(key),
            f"finalize: {outcome}; quarantine object left: {self.exists(key)}",
        )
        key, status = self.upload(
            OWNER_A, TRADE_A, "image/png", _png(), put_type="text/plain"
        )
        self.check(
            "signed Content-Type is enforced by R2",
            status in (400, 403) and not self.exists(key),
            f"PUT with a different Content-Type -> HTTP {status}",
        )

    def deletion(self, final_key):
        before = self.keys(f"u/{OWNER_A}/")
        self.storage.delete_trade_objects(OWNER_B, TRADE_A)
        intact = self.keys(f"u/{OWNER_A}/") == before and bool(before)
        self.storage.delete_trade_objects(OWNER_A, TRADE_A)
        gone = self.keys(f"u/{OWNER_A}/t/{TRADE_A}/") == []
        self.check(
            "trade deletion is owner-scoped",
            intact and gone,
            f"other owner's call left objects intact: {intact}; owner's call removed them: {gone}",
        )

    def cleanup(self):
        for prefix in self.test_prefixes():
            for key in self.keys(prefix):
                self.client.delete_object(Bucket=self.bucket, Key=key)
        left = {p: len(self.keys(p)) for p in self.test_prefixes()}
        self.check(
            "cleanup: test prefixes empty",
            not any(left.values()),
            f"objects left: {left}",
        )

    def all(self):
        leftovers = {p: len(self.keys(p)) for p in self.test_prefixes()}
        if any(leftovers.values()):
            raise Refused(f"test prefixes are not empty before the run: {leftovers}")
        try:
            self.lifecycle()
            self.cors()
            final_key = self.attach_and_download()
            self.cross_owner_and_abandon()
            self.rejection()
            if final_key:
                self.deletion(final_key)
        finally:
            self.cleanup()
        return self.results


def _configure(require_live: bool = True):
    bucket = os.getenv("R2_BUCKET", "")
    if require_live:
        if os.getenv("TRADELENS_R2_GATE_ALLOW") != "1":
            raise Refused("set TRADELENS_R2_GATE_ALLOW=1")
        if not bucket or bucket != os.getenv("TRADELENS_R2_EXPECT_BUCKET", ""):
            raise Refused("R2_BUCKET must equal TRADELENS_R2_EXPECT_BUCKET")
        production = os.getenv("TRADELENS_R2_PRODUCTION_BUCKET", "")
        if production and bucket == production:
            raise Refused("R2_BUCKET is the production bucket")
        for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
            if not os.getenv(name):
                raise Refused(f"{name} is not set")
    return bucket


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report")
    parser.add_argument("--max-quarantine-days", type=int, default=7)
    parser.add_argument("--plant-expiry-probe", action="store_true")
    parser.add_argument("--check-expiry-probe", metavar="KEY")
    args = parser.parse_args()

    scratch = tempfile.mkdtemp(prefix="gate6-")
    os.environ["DATABASE_URL"] = (
        f"sqlite:///{scratch}/gate6.db"  # never the app database
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        bucket = _configure()
    except Refused as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from src.tradelens.api import storage

    client = storage._client()
    if args.check_expiry_probe:
        key = args.check_expiry_probe
        if not key.startswith(f"quarantine/u/{OWNER_A}/"):
            print("REFUSED: not a probe key")
            return 2
        present = key in [
            o["Key"]
            for o in client.list_objects_v2(Bucket=bucket, Prefix=key).get(
                "Contents", []
            )
        ]
        print(
            f"{'FAIL' if present else 'PASS'}  expiry probe {'still present' if present else 'expired'}: {key}"
        )
        return 1 if present else 0
    _seed_owners()
    if args.plant_expiry_probe:
        key, status = Run(storage, client, bucket, "", 0).upload(
            OWNER_A, TRADE_A, "image/png", _png()
        )
        print(
            f"planted expiry probe (HTTP {status}): {key}\nrerun later with --check-expiry-probe '{key}'"
        )
        return 0 if status < 300 else 1
    site_origin = os.getenv("SITE_ORIGIN", "").rstrip("/")
    if not site_origin:
        print("REFUSED: SITE_ORIGIN is not set (needed for the CORS checks)")
        return 2
    try:
        results = Run(
            storage, client, bucket, site_origin, args.max_quarantine_days
        ).all()
    except Refused as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    failed = [r["check"] for r in results if r["result"] == "FAIL"]
    report = {"bucket_matches_expected": True, "results": results, "failed": failed}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2))
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
