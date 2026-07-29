"""
Ownership-scoped cleanup for the marketing-screenshot capture.

`--clean` runs a recursive delete, so it is the one part of the capture
script that can destroy something. It therefore takes ONE exact directory
and validates ownership before removing anything: no glob, no sweep, and
failures raised rather than swallowed.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from scripts.capture_app_screenshots import (
    CAPTURE_DIR_PREFIX,
    CAPTURE_MARKER,
    CHROME_PROFILE_DIRNAME,
    clean_capture_dir,
    main,
)

TEMP = Path(tempfile.gettempdir())


def _run_dir(name: str, marker: bool = True, db: bool = True) -> Path:
    """A directory shaped like a capture run, with parts optionally missing."""
    path = TEMP / f"{CAPTURE_DIR_PREFIX}{name}"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir()
    if marker:
        (path / CAPTURE_MARKER).write_text("x", encoding="utf-8")
    if db:
        (path / "capture.db").write_text("x", encoding="utf-8")
    (path / CHROME_PROFILE_DIRNAME).mkdir(exist_ok=True)
    (path / CHROME_PROFILE_DIRNAME / "Cookies").write_text("x", encoding="utf-8")
    return path


@pytest.fixture
def cleanup_paths():
    created: list[Path] = []
    yield created
    for path in created:
        if path.is_symlink():
            path.unlink(missing_ok=True)
        else:
            shutil.rmtree(path, ignore_errors=True)


def test_cleaning_one_run_leaves_a_concurrent_run_untouched(cleanup_paths):
    """The old implementation globbed the whole temp directory, so cleaning
    up after one capture deleted a second capture's database out from under
    it. Two runs must be independent."""
    run_a = _run_dir("aaa")
    run_b = _run_dir("bbb")
    cleanup_paths.extend([run_a, run_b])

    assert clean_capture_dir(run_a) == run_a.resolve()
    assert not run_a.exists()
    assert run_b.exists(), "cleaning run A removed run B"
    assert (run_b / "capture.db").exists()


def test_cleaning_removes_the_database_and_the_browser_profile(cleanup_paths):
    """One run owns one directory, so there is a single thing to delete."""
    run = _run_dir("both")
    cleanup_paths.append(run)
    assert (run / "capture.db").exists()
    assert (run / CHROME_PROFILE_DIRNAME / "Cookies").exists()

    clean_capture_dir(run)
    assert not run.exists()


def test_the_whole_temp_directory_is_refused():
    with pytest.raises(ValueError, match="direct child"):
        clean_capture_dir(TEMP)


def test_a_directory_without_our_prefix_is_refused(cleanup_paths):
    path = TEMP / "not-a-tradelens-capture"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir()
    (path / CAPTURE_MARKER).write_text("x", encoding="utf-8")
    (path / "capture.db").write_text("x", encoding="utf-8")
    cleanup_paths.append(path)
    with pytest.raises(ValueError, match="does not start with"):
        clean_capture_dir(path)
    assert path.exists()


def test_a_directory_without_the_ownership_marker_is_refused(cleanup_paths):
    """A name that merely matches the prefix does not authorise a delete."""
    run = _run_dir("unmarked", marker=False)
    cleanup_paths.append(run)
    with pytest.raises(ValueError, match="marker"):
        clean_capture_dir(run)
    assert run.exists()


def test_a_directory_without_capture_db_is_refused(cleanup_paths):
    run = _run_dir("nodb", db=False)
    cleanup_paths.append(run)
    with pytest.raises(ValueError, match="capture.db"):
        clean_capture_dir(run)
    assert run.exists()


def test_a_symlink_is_refused_before_it_is_resolved(cleanup_paths):
    """Resolving first and checking after would follow the link to a real
    run directory and delete its contents through the alias."""
    run = _run_dir("linktarget")
    link = TEMP / f"{CAPTURE_DIR_PREFIX}alias"
    link.unlink(missing_ok=True)
    link.symlink_to(run, target_is_directory=True)
    cleanup_paths.extend([link, run])

    with pytest.raises(ValueError, match="symlink"):
        clean_capture_dir(link)
    assert run.exists() and (run / "capture.db").exists()


def test_a_path_inside_the_workspace_is_refused():
    """Nothing in the repository is ever a capture run."""
    with pytest.raises(ValueError, match="direct child"):
        clean_capture_dir(Path(__file__).resolve().parents[1])


def test_a_nested_directory_is_refused_even_when_it_looks_owned(cleanup_paths):
    """Only a DIRECT child of the system temp directory qualifies, so no
    `..` segment or nested lookalike can walk the deletion elsewhere."""
    run = _run_dir("outer")
    nested = run / f"{CAPTURE_DIR_PREFIX}inner"
    nested.mkdir()
    (nested / CAPTURE_MARKER).write_text("x", encoding="utf-8")
    (nested / "capture.db").write_text("x", encoding="utf-8")
    cleanup_paths.append(run)

    with pytest.raises(ValueError, match="direct child"):
        clean_capture_dir(nested)
    assert nested.exists()


def test_a_missing_path_is_refused(cleanup_paths):
    with pytest.raises(OSError):
        clean_capture_dir(TEMP / f"{CAPTURE_DIR_PREFIX}never-existed")


def test_clean_requires_exactly_one_named_directory(capsys):
    """No argument means no sweep — the old behaviour deleted everything it
    could find."""
    assert main(["--clean"]) == 2
    assert "usage" in capsys.readouterr().err

    assert main(["--clean", "a", "b"]) == 2


def test_clean_reports_a_refusal_instead_of_raising(capsys, cleanup_paths):
    run = _run_dir("cli-unmarked", marker=False)
    cleanup_paths.append(run)
    assert main(["--clean", str(run)]) == 1
    assert "refused" in capsys.readouterr().err
    assert run.exists()


def test_clean_removes_a_valid_run_through_the_cli(capsys, cleanup_paths):
    run = _run_dir("cli-ok")
    cleanup_paths.append(run)
    assert main(["--clean", str(run)]) == 0
    assert "removed" in capsys.readouterr().out
    assert not run.exists()


def test_the_browser_profile_lives_inside_the_owned_run_directory():
    """One run, one owned directory. A profile in its own mktemp dir is a
    second thing to remember to delete — and 171MB of it.

    Seeded in a SUBPROCESS. seed_capture_db() repoints DATABASE_URL and
    purges src.tradelens from sys.modules, which mid-suite creates a second
    copy of ai_client and breaks every downstream `isinstance(x,
    AIUnavailable)` check — 53 unrelated failures when this ran in-process.
    Same reason app_boot_check.py is a subprocess.
    """
    import subprocess
    import sys as _sys

    from scripts.capture_app_screenshots import CHROME_PROFILE_DIRNAME

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            _sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r)\n"
            "from scripts.capture_app_screenshots import seed_capture_db\n"
            "print(seed_capture_db())" % str(root),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=root,
    )
    assert proc.returncode == 0, proc.stderr
    url = proc.stdout.strip().splitlines()[-1]

    run_dir = Path(url.replace("sqlite:///", "")).parent
    try:
        assert (run_dir / CHROME_PROFILE_DIRNAME).is_dir()
        assert (run_dir / CAPTURE_MARKER).is_file()
        assert (run_dir / "capture.db").exists()
    finally:
        clean_capture_dir(run_dir)
    assert not run_dir.exists()


def test_the_documented_sequence_stops_the_browser_before_cleaning():
    """A running Chrome keeps writing to its profile, so cleaning
    underneath it races. The docs have to stop it first — and stop only the
    processes this run started.

    `pkill -f "streamlit run"` matches by pattern, not by ownership: it
    kills the app a colleague, or you in another terminal, happens to have
    open. Same for any Chrome reusing the debugging port. So each process
    is backgrounded, its PID recorded, and only those PIDs signalled.
    """
    src = (
        Path(__file__).resolve().parents[1] / "scripts" / "capture_app_screenshots.py"
    ).read_text(encoding="utf-8")
    doc = src[: src.index('"""', src.index('"""') + 3)]
    # The runnable steps, not the prose above them: the paragraph that
    # explains WHY pattern-killing is unsafe has to be able to name it.
    workflow = doc[doc.index("Usage\n-----") :]
    # The lines the reader would RUN. The comments among them have to be
    # able to name the hazards they are warning about.
    commands = "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )

    assert "pkill" not in commands, "the workflow kills by pattern, not by PID"
    assert "killall" not in commands

    assert "APP_PID=$!" in doc, "the app's PID is not captured"
    assert "CHROME_PID=$!" in doc, "the browser's PID is not captured"

    # exact-PID shutdown, and a wait, before the delete
    clean_cmd = doc.index('--clean "$RUN_DIR"')
    for signal in ('kill "$CHROME_PID"', 'kill "$APP_PID"'):
        assert signal in doc, f"missing {signal}"
        assert doc.index(signal) < clean_cmd, f"{signal} runs after --clean"
    for waited in ('wait "$CHROME_PID"', 'wait "$APP_PID"'):
        assert waited in doc, f"missing {waited}"
        assert doc.index(waited) < clean_cmd, f"{waited} runs after --clean"

    # An interrupted or failed capture must still shut down and clean up.
    # The signal traps exit; only EXIT runs cleanup. `trap cleanup EXIT INT
    # TERM` does NOT exit on a signal in zsh — behaviour is proven in the
    # zsh subprocess tests below rather than asserted from source here.
    assert "trap cleanup EXIT\n" in commands, "no EXIT trap"
    assert "trap 'exit 130' INT" in commands, "SIGINT does not exit 130"
    assert "trap 'exit 143' TERM" in commands, "SIGTERM does not exit 143"
    assert "trap cleanup EXIT INT TERM" not in commands, (
        "the combined trap is back: in zsh it runs cleanup, RESUMES the "
        "script, and runs cleanup again through EXIT"
    )
    assert "trap - EXIT INT TERM" in commands, "cleanup does not disarm its own traps"

    # the profile stays inside the owned run directory
    assert '--user-data-dir="$RUN_DIR/chrome-profile"' in doc


def test_the_documented_run_directory_is_derived_not_pasted():
    """RUN_DIR used to appear as a placeholder BEFORE --seed produced it,
    so the sequence could not be run as written. It is derived from the URL
    --seed prints — verified against a real macOS temp path, which is
    /var/folders/... and so yields a four-slash sqlite URL."""
    src = (
        Path(__file__).resolve().parents[1] / "scripts" / "capture_app_screenshots.py"
    ).read_text(encoding="utf-8")
    doc = src[: src.index('"""', src.index('"""') + 3)]

    seed = doc.index("--seed)")
    assert doc.index('RUN_DIR="${DB_URL#sqlite:///}"') > seed
    assert 'RUN_DIR="${RUN_DIR%/capture.db}"' in doc
    assert "tradelens-capture-XXXX" not in doc, "a placeholder path is back"

    # the derivation, exercised on the shape --seed actually emits
    url = "sqlite:////var/folders/t1/x/T/tradelens-capture-abc123/capture.db"
    derived = url[len("sqlite:///") :]
    derived = derived[: -len("/capture.db")]
    assert derived == "/var/folders/t1/x/T/tradelens-capture-abc123"
    assert derived.startswith("/"), "the leading slash was eaten"


def test_there_is_no_sweep_left_anywhere():
    """The old implementation globbed the system temp directory."""
    src = (
        Path(__file__).resolve().parents[1] / "scripts" / "capture_app_screenshots.py"
    ).read_text(encoding="utf-8")
    assert "clean_capture_dirs" not in src
    assert "gettempdir()).glob" not in src
    assert "ignore_errors=True" not in src


# ---------------------------------------------------------------------------
# The documented trap, executed.
#
# `trap cleanup EXIT INT TERM` is a plausible-looking line that is wrong in
# zsh: a signal runs cleanup, then execution RESUMES and cleanup runs again
# through EXIT. Measured directly — SIGINT produced "cleanup, after-int,
# cleanup" and exited 0, so an interrupted capture would have continued
# through the remaining steps and reported success.
#
# Reading the docstring cannot catch that, so these run the documented
# shape under a real zsh and assert on what the shell actually does.
# ---------------------------------------------------------------------------

_ZSH_HARNESS = """
set -eu
cleanup() {
    TL_CAPTURE_STATUS=$?
    trap - EXIT INT TERM
    print -r -- "cleanup"
    if [ "${FAIL_CLEANUP:-0}" = "1" ]; then TL_CAPTURE_STATUS=9; fi
    exit "$TL_CAPTURE_STATUS"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

case "${MODE}" in
  normal) : ;;
  int)    kill -INT $$;  print -r -- "after-signal" ;;
  term)   kill -TERM $$; print -r -- "after-signal" ;;
  fail)   sh -c 'exit 7' ;;
esac
print -r -- "body-end"
"""


def _run_zsh(mode: str, **env_extra) -> tuple[int, str]:
    import os
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    if zsh is None:  # pragma: no cover - zsh is present on macOS and CI
        pytest.skip("zsh is not available")
    env = {**os.environ, "MODE": mode, **env_extra}
    proc = subprocess.run(
        [zsh, "-c", _ZSH_HARNESS], capture_output=True, text=True, env=env, timeout=60
    )
    return proc.returncode, proc.stdout


def test_a_normal_run_cleans_up_once_and_succeeds():
    status, out = _run_zsh("normal")
    assert out.count("cleanup") == 1, out
    assert "body-end" in out
    assert status == 0


def test_sigint_cleans_up_once_exits_130_and_runs_nothing_after():
    """The defect this replaces: the script carried on past the signal."""
    status, out = _run_zsh("int")
    assert out.count("cleanup") == 1, f"cleanup ran {out.count('cleanup')} times: {out}"
    assert "after-signal" not in out, "execution resumed after SIGINT"
    assert "body-end" not in out, "the body completed after SIGINT"
    assert status == 130, status


def test_sigterm_cleans_up_once_exits_143_and_runs_nothing_after():
    status, out = _run_zsh("term")
    assert out.count("cleanup") == 1, f"cleanup ran {out.count('cleanup')} times: {out}"
    assert "after-signal" not in out, "execution resumed after SIGTERM"
    assert "body-end" not in out, "the body completed after SIGTERM"
    assert status == 143, status


def test_a_failing_body_cleans_up_once_and_keeps_its_own_status():
    """A capture that failed must not be reported as a success just because
    the tidy-up worked."""
    status, out = _run_zsh("fail")
    assert out.count("cleanup") == 1, out
    assert "body-end" not in out
    assert status == 7, status


def test_a_failing_cleanup_becomes_the_final_status():
    """Leaving a seeded database behind is a failure, even when the capture
    itself worked."""
    status, out = _run_zsh("normal", FAIL_CLEANUP="1")
    assert out.count("cleanup") == 1, out
    assert status == 9, status


def test_the_combined_trap_really_is_broken_in_zsh():
    """Pins the reason the shape above is written the way it is. If a zsh
    release ever makes the combined form exit on a signal, this fails and
    the workaround can be reconsidered — rather than surviving as folklore.
    """
    import shutil
    import subprocess

    zsh = shutil.which("zsh")
    if zsh is None:  # pragma: no cover
        pytest.skip("zsh is not available")
    proc = subprocess.run(
        [
            zsh,
            "-c",
            "cleanup() { print -r -- cleanup; }\n"
            "trap cleanup EXIT INT TERM\n"
            "kill -INT $$\n"
            "print -r -- after-signal\n",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.stdout.count("cleanup") == 2, proc.stdout
    assert "after-signal" in proc.stdout
    assert proc.returncode == 0
