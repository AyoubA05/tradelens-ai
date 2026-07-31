"""
Capture the marketing site's in-app product screenshots from the real app.

The four images on the marketing site are the only place a prospective user
sees the product before signing up, so they are generated from a running
instance rather than mocked up — a screenshot that flatters a screen the
product does not have is a promise the product cannot keep.

Each capture is written at the exact pixel dimensions the marketing HTML
declares in its `width`/`height` attributes. Those attributes reserve the
image's box before it loads; a file whose real size disagrees with them
changes the page's aspect ratio and shifts the layout as it arrives, which
is the cumulative-layout-shift the attributes exist to prevent. The sizes
are asserted here, not assumed, and `verify()` re-reads what was written.

Isolation
---------
The capture NEVER touches the development database. `seed_capture_db()`
builds a throwaway SQLite file, seeds user 1 with the ICT/SMC starter
playbook and the sample trades, and the app is pointed at it through
DATABASE_URL. A marketing shot should show a product with a strategy
configured — but not at the price of writing rows into whatever database
the developer happens to be working in.

One run owns ONE directory: the database, the ownership marker and the
disposable browser profile all live inside it, so there is a single thing
to delete and `--clean` can refuse anything it does not own. The signed
token is never printed — it grants a session, so echoing it into a
terminal, a CI log or a scrollback is handing out access.

Only the processes this run started are ever stopped. `pkill -f "streamlit
run"` would also kill the app a colleague — or you, in another terminal —
happens to have open, and `pkill -f remote-debugging-port=9333` kills any
Chrome that reuses the port. Both are matched by pattern, not by ownership.
Each process is therefore started in the background, its PID recorded, and
only those PIDs are signalled.

Usage
-----
    set -eu

    # 1. build an isolated capture run, and DERIVE the run directory from
    #    the URL --seed printed, so there is nothing to paste by hand
    DB_URL="$(python scripts/capture_app_screenshots.py --seed)"
    RUN_DIR="${DB_URL#sqlite:///}"
    RUN_DIR="${RUN_DIR%/capture.db}"

    # 2. shut down exactly what this run started, however it ends —
    #    interrupted, failed, or finished — and only then clean up.
    #
    #    The signal traps EXIT rather than doing the work themselves. In
    #    zsh, `trap cleanup EXIT INT TERM` does NOT exit on INT or TERM:
    #    it runs cleanup, resumes the script, and runs cleanup AGAIN via
    #    EXIT. Measured — a Ctrl-C printed `cleanup, after-int, cleanup`
    #    and exited 0, so an interrupted capture would have carried on
    #    through the remaining steps and reported success.
    #
    #    cleanup() clears every trap before it does anything, so it cannot
    #    re-enter. ${VAR:-} keeps it safe under `set -u` when it fires
    #    before a PID exists.
    cleanup() {
        TL_CAPTURE_STATUS=$?
        trap - EXIT INT TERM

        [ -n "${CHROME_PID:-}" ] && kill "$CHROME_PID" 2>/dev/null || true
        [ -n "${APP_PID:-}" ] && kill "$APP_PID" 2>/dev/null || true
        [ -n "${CHROME_PID:-}" ] && wait "$CHROME_PID" 2>/dev/null || true
        [ -n "${APP_PID:-}" ] && wait "$APP_PID" 2>/dev/null || true

        python scripts/capture_app_screenshots.py \
            --clean "$RUN_DIR" || TL_CAPTURE_STATUS=$?

        exit "$TL_CAPTURE_STATUS"
    }

    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    # 3. start the app against THAT database, never the dev one
    TRADELENS_SESSION_SECRET=<secret> DEMO_MODE=true \
        DATABASE_URL="$DB_URL" \
        streamlit run src/tradelens/ui/app.py \
        --server.headless true --server.port 8599 &
    APP_PID=$!

    # 4. start headless Chrome on the profile INSIDE the run directory
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
        --headless=new --remote-debugging-port=9333 \
        --user-data-dir="$RUN_DIR/chrome-profile" about:blank &
    CHROME_PID=$!

    # 5. capture. The trap then stops exactly $CHROME_PID and $APP_PID,
    #    WAITS for them — a running Chrome keeps writing to its profile, so
    #    cleaning underneath it races — and removes the one run directory,
    #    database and browser profile together.
    TRADELENS_SESSION_SECRET=<secret> python scripts/capture_app_screenshots.py

The same starter playbook and the same sample set every run, so the shots
are reproducible. `--clean` takes one exact path and validates ownership
before deleting anything; there is deliberately no sweep.

The session secret must match the one the app is running with: the script
mints a signed token so the capture shows the signed-in product rather than
the login screen.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_URL = os.environ.get("TL_CAPTURE_APP", "http://localhost:8599")
CDP_URL = os.environ.get("TL_CAPTURE_CDP", "http://127.0.0.1:9333")

# (name, app route, output path, width, height, css_scale)
#
# The dimensions mirror the width/height attributes in site/index.html.
# test_marketing_screenshots_match_their_declared_dimensions keeps the two
# in step, so changing one without the other fails the suite.
#
# css_scale enlarges the BROWSER viewport by that factor while keeping the
# declared aspect ratio exactly, then the capture is downsampled back into
# the box. It is how a tall page fits a landscape frame without cropping
# through the middle of a chart: at 1.0 the Overview's equity curve and the
# Analytics chart were both sliced by the bottom edge, on shots whose own
# alt text promises them. Scaling the viewport instead of stretching the
# image keeps every proportion true — only the apparent zoom changes.
CAPTURES = (
    ("overview", "/", "site/assets/shot-dashboard-wide.webp", 1600, 1000, 1.30),
    ("new-trade", "/NewTrade", "site/assets/shot-newtrade.webp", 1400, 933, 1.00),
    ("analytics", "/Analytics", "site/assets/shot-analytics.webp", 1400, 933, 1.32),
    ("strategy", "/Strategy", "site/assets/shot-strategy.webp", 1400, 933, 1.34),
)

# Optional per-shot preparation, run after the page settles and before the
# shutter. The playbook reads as a list of closed drawers until one is
# open — a prospective user should see that a rule section holds real
# sentences, not just that the section exists.
PREPARE = {
    "strategy": (
        "(()=>{const d=[...document.querySelectorAll("
        "'[data-testid=\"stExpander\"] details')]"
        ".find(x=>/Entry Rules/.test(x.textContent));"
        "if(d && !d.open) d.querySelector('summary').click();"
        "return !!d;})()"
    ),
}

# Streamlit renders progressively; the marker is the page masthead, which
# only exists once the destination itself has drawn.
_READY = "!!document.querySelector('.tl-masthead-title, .tl-section-title')"
_SETTLE_SECONDS = 3.0
_WEBP_QUALITY = 82


CAPTURE_DIR_PREFIX = "tradelens-capture-"
# Written into every run directory this script creates. --clean refuses to
# delete a directory that does not carry it, so a name that merely matches
# the prefix is not enough to authorise a recursive delete.
CAPTURE_MARKER = ".tradelens-capture-run"
CHROME_PROFILE_DIRNAME = "chrome-profile"
CAPTURE_USER_ID = 1
CAPTURE_USERNAME = "ayoub"


def _token() -> str:
    """A signed session token, so the capture shows the product signed in.

    Deliberately never printed or written to a file. It grants a session:
    echoing it into a terminal, a CI log or a shell scrollback is handing
    out access to the account it was minted for.
    """
    from src.tradelens.ui.components.auth import _issue_token

    return _issue_token(os.environ.get("TL_CAPTURE_USER", CAPTURE_USERNAME), 1)


def starter_playbook() -> dict:
    """The ICT/SMC starter playbook, read from the page that owns it.

    Parsed out of the module's AST rather than copied here, because a
    second copy is a second thing to keep in step — and the page cannot be
    imported (it runs Streamlit at import time).
    """
    import ast

    page = ROOT / "src" / "tradelens" / "ui" / "pages" / "5_Strategy.py"
    tree = ast.parse(page.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "STARTER_TEMPLATE" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise RuntimeError("STARTER_TEMPLATE is no longer defined in 5_Strategy.py")


def seed_capture_db(directory: Path | None = None) -> str:
    """Build a throwaway database for the capture. Returns its DATABASE_URL.

    An isolated file, never the developer's working database: a marketing
    shot needs a configured strategy and sample trades, and creating those
    is a write. Reproducible — the same starter playbook and the same
    sample set every run — and it fails loudly rather than quietly
    capturing an empty product.
    """
    import tempfile

    directory = directory or Path(tempfile.mkdtemp(prefix=CAPTURE_DIR_PREFIX))
    directory.mkdir(parents=True, exist_ok=True)
    # The ownership marker, and the browser profile directory beside the
    # database — one run, one owned directory, one thing to delete.
    (directory / CAPTURE_MARKER).write_text(
        "Created by scripts/capture_app_screenshots.py. Safe to delete.\n",
        encoding="utf-8",
    )
    (directory / CHROME_PROFILE_DIRNAME).mkdir(exist_ok=True)
    url = f"sqlite:///{directory / 'capture.db'}"

    os.environ["DATABASE_URL"] = url
    for module in [m for m in sys.modules if m.startswith("src.tradelens")]:
        del sys.modules[module]

    from src.tradelens.db.init_db import init_db

    init_db()

    from src.tradelens.db.models import User
    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services.sample_data import load_sample_trades
    from src.tradelens.services.strategy import (
        get_active_strategy,
        upsert_strategy_profile,
    )

    session = SessionLocal()
    session.add(User(id=CAPTURE_USER_ID, username=CAPTURE_USERNAME, password_hash="x"))
    session.commit()
    session.close()

    upsert_strategy_profile(CAPTURE_USER_ID, **starter_playbook())
    trades = load_sample_trades(CAPTURE_USER_ID)

    # Fail here rather than 40 seconds later with four screenshots of an
    # empty product. Every marketing claim below depends on both of these.
    active = get_active_strategy(CAPTURE_USER_ID)
    if not active or not (active.get("name") or "").strip():
        raise RuntimeError("capture db has no active strategy after seeding")
    missing = [
        field
        for field in starter_playbook()
        if not str(active.get(field) or "").strip()
    ]
    if missing:
        raise RuntimeError(f"capture db strategy is incomplete: {missing}")
    if trades < 1:
        raise RuntimeError("capture db has no sample trades after seeding")

    return url


def clean_capture_dir(path: str | Path) -> Path:
    """Delete ONE capture run directory, named exactly, or raise.

    Recursive deletion driven by a glob over the system temp directory is
    the wrong shape for this: it deletes a concurrent run's database out
    from under it, and one edited prefix away it deletes something that was
    never ours. So the caller names the directory, and every one of these
    has to hold before anything is removed:

      * it resolves to a DIRECT child of the system temp directory, so no
        `..` segment or symlinked parent can walk the deletion elsewhere;
      * the name carries our prefix;
      * it is a real directory, not a symlink to one;
      * it holds our ownership marker, so a directory that merely matches
        the prefix is still refused;
      * it holds capture.db, so a half-built or unrelated directory is too.

    Failures are raised, never swallowed: a cleanup that silently leaves a
    seeded database behind is how a stale one gets captured next time.
    """
    import shutil
    import tempfile

    target = Path(path).expanduser()
    if target.is_symlink():
        raise ValueError(f"refusing to clean a symlink: {target}")
    target = target.resolve(strict=True)
    temp_root = Path(tempfile.gettempdir()).resolve()

    if target.parent != temp_root:
        raise ValueError(
            f"refusing to clean {target}: not a direct child of {temp_root}"
        )
    if not target.name.startswith(CAPTURE_DIR_PREFIX):
        raise ValueError(
            f"refusing to clean {target}: name does not start with "
            f"{CAPTURE_DIR_PREFIX!r}"
        )
    if not target.is_dir():
        raise ValueError(f"refusing to clean {target}: not a directory")
    marker = target / CAPTURE_MARKER
    if not marker.is_file():
        raise ValueError(f"refusing to clean {target}: no {CAPTURE_MARKER} marker")
    if not (target / "capture.db").exists():
        raise ValueError(f"refusing to clean {target}: no capture.db")

    shutil.rmtree(target)
    return target


class _Tab:
    """One CDP tab. Small enough not to want a dependency for it."""

    def __init__(self, url: str) -> None:
        from tornado.websocket import websocket_connect

        request = urllib.request.Request(f"{CDP_URL}/json/new?{url}", method="PUT")
        self._info = json.load(urllib.request.urlopen(request, timeout=20))
        self._connect = websocket_connect(self._info["webSocketDebuggerUrl"])
        self._id = 0
        self._conn = None

    async def open(self):
        self._conn = await self._connect
        return self

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        wanted = self._id
        self._conn.write_message(
            json.dumps({"id": wanted, "method": method, "params": params or {}})
        )
        while True:
            message = json.loads(await self._conn.read_message())
            if message.get("id") == wanted:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    async def js(self, expression: str):
        result = await self.send(
            "Runtime.evaluate", {"expression": expression, "returnByValue": True}
        )
        return result.get("result", {}).get("value")


async def _capture_one(name, route, out_path, width, height, css_scale, token) -> Path:
    tab = await _Tab(f"{APP_URL}{route}?auth={token}").open()
    # Same aspect ratio as the declared box, scaled up so more of a tall
    # page fits. deviceScaleFactor 2 on top of that, so the WebP is
    # downsampled from a much denser capture; text taken at 1x and shown on
    # a retina display looks soft.
    view_w = round(width * css_scale)
    view_h = round(height * css_scale)
    await tab.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": view_w, "height": view_h, "deviceScaleFactor": 2, "mobile": False},
    )
    # Marketing stills must not catch a mid-flight entrance animation.
    await tab.send(
        "Emulation.setEmulatedMedia",
        {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
    )

    for _ in range(40):
        time.sleep(1.2)
        if await tab.js(_READY):
            break
    else:
        raise RuntimeError(f"{name}: the page never rendered a masthead")

    time.sleep(_SETTLE_SECONDS)

    if name in PREPARE:
        if not await tab.js(PREPARE[name]):
            raise RuntimeError(f"{name}: preparation step found nothing to do")
        time.sleep(1.5)

    if await tab.js("!!document.querySelector('[data-testid=\"stException\"]')"):
        raise RuntimeError(f"{name}: the page rendered an exception")

    shot = await tab.send(
        "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
    )
    raw = base64.b64decode(shot["data"])

    from PIL import Image

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    # Downsample the 2x capture to the declared box.
    if image.size != (width, height):
        image = image.resize((width, height), Image.LANCZOS)

    destination = ROOT / out_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "WEBP", quality=_WEBP_QUALITY, method=6)
    return destination


def verify() -> list[str]:
    """Re-read what was written. Returns a list of problems, empty if clean."""
    from PIL import Image

    problems: list[str] = []
    for name, _route, out_path, width, height, _scale in CAPTURES:
        path = ROOT / out_path
        if not path.exists():
            problems.append(f"{name}: {out_path} was not written")
            continue
        with Image.open(path) as image:
            if image.format != "WEBP":
                problems.append(f"{name}: {image.format}, expected WEBP")
            if image.size != (width, height):
                problems.append(
                    f"{name}: {image.size} does not match the "
                    f"declared {(width, height)}"
                )
    return problems


async def _assert_app_shows_the_seeded_strategy(token: str) -> None:
    """The app under capture must be the seeded one, not the dev database.

    Every marketing claim on these four shots depends on an active
    strategy: the Overview and New Trade rails say which playbook is in
    force, and the Analytics Strategy filter is empty without one. Checked
    against the RUNNING app, because a correctly seeded database the app
    was never pointed at would still produce four empty screenshots.
    """
    tab = await _Tab(f"{APP_URL}/?auth={token}").open()
    await tab.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1600, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
    )
    for _ in range(40):
        time.sleep(1.2)
        if await tab.js(_READY):
            break
    note = await tab.js(
        "(()=>{const e=document.querySelector('.tl-side-note');"
        "return e?e.textContent.trim():'';})()"
    )
    if "No active strategy" in (note or ""):
        raise RuntimeError(
            "the running app shows no active strategy — it is not pointed at "
            "a seeded capture database (see --seed / --capture-all)"
        )


async def _main() -> int:
    token = _token()
    await _assert_app_shows_the_seeded_strategy(token)
    for name, route, out_path, width, height, css_scale in CAPTURES:
        destination = await _capture_one(
            name, route, out_path, width, height, css_scale, token
        )
        print(f"  {name:<10} -> {destination.relative_to(ROOT)}")
    problems = verify()
    for problem in problems:
        print(f"  FAIL {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--seed" in argv:
        # The URL and the run directory are safe to print; the session
        # token never is.
        url = seed_capture_db()
        print(url)
        print(f"run-dir: {Path(url.replace('sqlite:///', '')).parent}", file=sys.stderr)
        return 0

    if "--clean" in argv:
        # The directory has to be named. There is no sweep: a glob over the
        # system temp directory deletes a concurrent run's database, and one
        # edited prefix away it deletes something that was never ours.
        rest = [a for a in argv if a != "--clean"]
        if len(rest) != 1:
            print(
                "usage: --clean <capture-run-dir>\n"
                "       the exact directory printed by --seed",
                file=sys.stderr,
            )
            return 2
        try:
            print(f"  removed {clean_capture_dir(rest[0])}")
        except (OSError, ValueError) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        return 0

    from tornado.ioloop import IOLoop

    return IOLoop.current().run_sync(_main)


if __name__ == "__main__":
    sys.exit(main())
