"""gate_r2_verify's checks pass on a correct fake R2 and FAIL on each broken one."""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _run(variant):
    env = {k: v for k, v in os.environ.items() if not k.startswith("R2_")}
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "r2_gate_fake_check.py"), variant],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_check_passes_against_a_correctly_configured_bucket():
    results = _run("correct")
    assert results and set(results.values()) == {"PASS"}, results
    assert len(results) == 11


def test_a_missing_lifecycle_rule_fails():
    assert _run("no-lifecycle")["quarantine lifecycle rule"] == "FAIL"


def test_an_expiry_rule_that_reaches_final_screenshots_fails():
    assert _run("bucket-wide-expiry")["quarantine lifecycle rule"] == "FAIL"


def test_a_wildcard_cors_origin_fails():
    results = _run("wildcard-cors")
    assert results["CORS configuration"] == "FAIL"
    assert results["CORS live preflight"] == "FAIL"


def test_unenforced_signed_content_type_fails():
    assert (
        _run("unsigned-content-type")["signed Content-Type is enforced by R2"] == "FAIL"
    )


def test_the_script_refuses_without_explicit_opt_in():
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("R2_", "TRADELENS_R2"))
    }
    result = subprocess.run(
        [sys.executable, "scripts/gate_r2_verify.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "REFUSED" in result.stdout


def test_the_production_bucket_is_refused():
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("R2_", "TRADELENS_R2"))
        },
        "TRADELENS_R2_GATE_ALLOW": "1",
        "R2_BUCKET": "prod",
        "TRADELENS_R2_EXPECT_BUCKET": "prod",
        "TRADELENS_R2_PRODUCTION_BUCKET": "prod",
    }
    result = subprocess.run(
        [sys.executable, "scripts/gate_r2_verify.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "production bucket" in result.stdout
