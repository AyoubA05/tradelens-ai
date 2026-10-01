"""The production-gates workflow's secret-output protections stay in place.

Each one closes a path found by the canary audit of 2026-09-29 (recorded in
docs/superpowers/gates/2026-09-21-production-gates.md). Removing any of them
must fail CI, not wait for the next audit to notice.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-gates.yml"


def _wf():
    return yaml.safe_load(WORKFLOW.read_text())


def _steps(job):
    return _wf()["jobs"][job]["steps"]


def _index(steps, predicate):
    return next(i for i, s in enumerate(steps) if predicate(s))


def test_the_workflow_only_runs_when_triggered_by_hand():
    wf = _wf()
    triggers = wf.get(True, wf.get("on"))
    assert list(triggers) == ["workflow_dispatch"]


def test_inputs_and_secrets_never_reach_a_shell_command_directly():
    for name, job in _wf()["jobs"].items():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), (name, step.get("name"))


def test_every_gate_job_takes_secrets_from_the_protected_environment():
    for name, job in _wf()["jobs"].items():
        assert job.get("environment") == "production-gates", name


def test_gate1_masks_derived_password_forms_before_running_short_tracebacks():
    steps = _steps("gate1-postgres")
    mask = _index(steps, lambda s: "::add-mask::" in s.get("run", ""))
    tests = _index(steps, lambda s: "pytest" in s.get("run", ""))
    assert mask < tests
    run = steps[tests]["run"]
    assert "--tb=short" in run
    assert "--showlocals" not in run and " -l " not in run


def test_gate3_records_no_traces_and_always_deletes_test_results():
    steps = _steps("gate3-playwright")
    tests = _index(steps, lambda s: "playwright test" in s.get("run", ""))
    assert "--trace=off" in steps[tests]["run"]
    cleanup = _index(steps, lambda s: "rm -rf test-results" in s.get("run", ""))
    publish = _index(steps, lambda s: s.get("name", "").startswith("Publish Gate 3"))
    assert tests < cleanup < publish
    assert steps[cleanup].get("if") == "always()"
    assert not any("upload-artifact" in s.get("uses", "") for s in steps)


def test_gate2_scans_its_report_for_the_key_before_uploading():
    steps = _steps("gate2-anthropic")
    scan = _index(steps, lambda s: "report contained the API key" in s.get("run", ""))
    upload = _index(steps, lambda s: "upload-artifact" in s.get("uses", ""))
    assert scan < upload and steps[scan].get("if") == "always()"


def _gate2_scan_code():
    run = next(
        s["run"]
        for s in _steps("gate2-anthropic")
        if "report contained the API key" in s.get("run", "")
    )
    return run.split("<<'PY'\n", 1)[1].rsplit("PY", 1)[0]


def test_gate2_scan_deletes_a_report_that_contains_the_key(tmp_path):
    key = "sk-ant-api03-LOCKIN-canary_x"
    report = tmp_path / "gate2.json"
    import base64

    encoded_b64 = base64.b64encode(key.encode()).decode().rstrip("=")
    for leaked in (key, key.replace("_", "%5F").replace("-", "%2D"), encoded_b64):
        report.write_text(json.dumps({"steps": [{"outcome": f"error {leaked}"}]}))
        env = {**os.environ, "ANTHROPIC_API_KEY": key}
        result = subprocess.run(
            [sys.executable, "-c", _gate2_scan_code()],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1 and not report.exists()
        assert key not in result.stdout + result.stderr
    report.write_text(json.dumps({"steps": [{"outcome": "completed"}]}))
    env = {**os.environ, "ANTHROPIC_API_KEY": key}
    clean = subprocess.run(
        [sys.executable, "-c", _gate2_scan_code()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert clean.returncode == 0 and report.exists()


def test_gate6_failures_print_the_exception_type_only(monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "gate_r2_verify", ROOT / "scripts" / "gate_r2_verify.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = (
        "https://canaryacct.r2.cloudflarestorage.com/bucket?X-Amz-Credential=CANARYAKID"
    )

    def boom(args, bucket):
        raise ConnectionError(secret)

    monkeypatch.setattr(module, "_run", boom)
    monkeypatch.setattr(module, "_configure", lambda: "gate-test")
    monkeypatch.setattr(sys, "argv", ["gate_r2_verify.py"])
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert module.main() == 1
    out = capsys.readouterr()
    assert "ConnectionError" in out.out
    assert (
        "canaryacct" not in out.out + out.err and "CANARYAKID" not in out.out + out.err
    )
