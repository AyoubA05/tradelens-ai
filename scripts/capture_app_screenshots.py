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
    TRADELENS_SESSION_SECRET=<secret> \
        ANTHROPIC_API_KEY=capture-only-placeholder DEMO_MODE=false \
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
    TRADELENS_SESSION_SECRET=<secret> \
        python scripts/capture_app_screenshots.py --all

The same starter playbook and the same sample set, anchored to 2026-08-09,
every run, so the shots are reproducible. The placeholder API key makes the
Partner launcher available for presentation but is never used to send a turn.
`--clean` takes one exact path and validates ownership before deleting
anything; there is deliberately no sweep.

The session secret must match the one the app is running with: the script
mints a signed token so the capture shows the signed-in product rather than
the login screen.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tradelens.ui.components.strategy_profile import demo_strategy_profile

APP_URL = os.environ.get("TL_CAPTURE_APP", "http://localhost:8599")
CDP_URL = os.environ.get("TL_CAPTURE_CDP", "http://127.0.0.1:9333")


@dataclass(frozen=True)
class CaptureSpec:
    name: str
    route: str
    output: Path
    width: int
    height: int
    coarse_pointer: bool = False
    open_partner: bool = False


# Fixed evidence, not a moving sample. A later rerun must reproduce the same
# dates rather than quietly presenting a different account history.
CAPTURE_ANCHOR = dt.date(2026, 8, 9)
AUDIT_DIR = Path("docs/superpowers/audits/assets/2026-08-09")

MARKETING_CAPTURES = (
    CaptureSpec(
        "overview", "/", Path("site/assets/shot-dashboard-wide.webp"), 1600, 1000
    ),
    CaptureSpec(
        "new-trade", "/NewTrade", Path("site/assets/shot-newtrade.webp"), 1400, 933
    ),
    CaptureSpec(
        "analytics", "/Analytics", Path("site/assets/shot-analytics.webp"), 1400, 933
    ),
    CaptureSpec(
        "strategy", "/Strategy", Path("site/assets/shot-strategy.webp"), 1400, 933
    ),
)

AUDIT_CAPTURES = (
    CaptureSpec(
        "overview-desktop", "/", AUDIT_DIR / "overview-desktop.png", 1440, 1000
    ),
    CaptureSpec(
        "new-trade-desktop",
        "/NewTrade",
        AUDIT_DIR / "new-trade-desktop.png",
        1440,
        1000,
    ),
    CaptureSpec(
        "journal-desktop", "/Trades", AUDIT_DIR / "journal-desktop.png", 1440, 1000
    ),
    CaptureSpec(
        "analytics-desktop",
        "/Analytics",
        AUDIT_DIR / "analytics-desktop.png",
        1440,
        1000,
    ),
    CaptureSpec(
        "ai-reviews-desktop",
        "/Insights",
        AUDIT_DIR / "ai-reviews-desktop.png",
        1440,
        1000,
    ),
    CaptureSpec(
        "strategy-desktop",
        "/Strategy",
        AUDIT_DIR / "strategy-desktop.png",
        1440,
        1000,
    ),
    CaptureSpec(
        "settings-desktop",
        "/Settings",
        AUDIT_DIR / "settings-desktop.png",
        1440,
        1000,
    ),
    CaptureSpec(
        "partner-drawer-desktop",
        "/",
        AUDIT_DIR / "partner-drawer-desktop.png",
        1440,
        1000,
        open_partner=True,
    ),
    CaptureSpec(
        "partner-page-phone",
        "/Partner",
        AUDIT_DIR / "partner-page-phone.png",
        375,
        812,
        coarse_pointer=True,
    ),
)

# The marketing frames intentionally show more CSS pixels than their output
# boxes. The aspect ratio never changes and there is no crop; a dense 2x
# screenshot is downsampled into the exact dimensions declared by site HTML.
_MARKETING_VIEWPORT_SCALE = {
    "overview": 1.30,
    "new-trade": 1.00,
    "analytics": 1.32,
    "strategy": 1.34,
}

# Compatibility for the two long-standing marketing contracts. New capture
# behavior consumes the typed manifests above.
CAPTURES = tuple(
    (
        capture.name,
        capture.route,
        capture.output.as_posix(),
        capture.width,
        capture.height,
        _MARKETING_VIEWPORT_SCALE[capture.name],
    )
    for capture in MARKETING_CAPTURES
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
_PARTNER_LAUNCHER = ".st-key-tl_partner_launcher button"
_PARTNER_DRAWER_HEADING = ".st-key-tl_partner_drawer .tl-partner-title"

_PAGE_STATE = """
(() => ({
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  exceptionCount: document.querySelectorAll('[data-testid="stException"]').length,
  coarse: matchMedia('(pointer: coarse)').matches,
  reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  scrollTop: Math.max(
    document.scrollingElement?.scrollTop || 0,
    document.querySelector('[data-testid="stMain"]')?.scrollTop || 0
  ),
  frameworkChromeCount: [...document.querySelectorAll(
    '[data-testid="stExpandSidebarButton"]'
  )].filter(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0 && rect.right > 0
      && rect.bottom > 0 && rect.left < innerWidth && rect.top < innerHeight;
  }).length,
  text: document.body.innerText,
  url: location.href,
}))()
"""


CAPTURE_DIR_PREFIX = "tradelens-capture-"
# Written into every run directory this script creates. --clean refuses to
# delete a directory that does not carry it, so a name that merely matches
# the prefix is not enough to authorise a recursive delete.
CAPTURE_MARKER = ".tradelens-capture-run"
CHROME_PROFILE_DIRNAME = "chrome-profile"
CAPTURE_USER_ID = 1
CAPTURE_USERNAME = "ayoub"


def redact_url(url: str) -> str:
    """Keep route geometry in diagnostics without exposing query values."""
    parts = urlsplit(url)
    query = urlencode([(key, "REDACTED") for key, _value in parse_qsl(parts.query)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def capture_mode(argv: list[str]) -> str:
    """Resolve the one intentional capture mode or refuse an ambiguous run."""
    selected = [mode for mode in ("marketing", "audit", "all") if f"--{mode}" in argv]
    if len(selected) != 1:
        raise ValueError("choose exactly one of --marketing, --audit, or --all")
    extras = [arg for arg in argv if arg not in {f"--{selected[0]}"}]
    if extras:
        raise ValueError(f"unrecognized capture arguments: {extras}")
    return selected[0]


def center_of_box(box: tuple[float, ...] | list[float]) -> tuple[float, float]:
    """Return the center of a CDP quadrilateral."""
    if len(box) != 8:
        raise ValueError("CDP box must contain four x/y points")
    return (
        sum(float(box[index]) for index in (0, 2, 4, 6)) / 4,
        sum(float(box[index]) for index in (1, 3, 5, 7)) / 4,
    )


def _dates_in_text(text: str) -> set[dt.date]:
    dates: set[dt.date] = set()
    month = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)"
    )
    patterns = (
        (r"\b\d{4}-\d{2}-\d{2}\b", "%Y-%m-%d"),
        (r"\b\d{4}/\d{2}/\d{2}\b", "%Y/%m/%d"),
        (r"\b\d{1,2}/\d{1,2}/\d{4}\b", "%m/%d/%Y"),
        (
            rf"\b{month} \d{{1,2}}, \d{{4}}\b",
            None,
        ),
    )
    for pattern, date_format in patterns:
        for value in re.findall(pattern, text):
            formats = (date_format,) if date_format else ("%b %d, %Y", "%B %d, %Y")
            for candidate in formats:
                try:
                    dates.add(dt.datetime.strptime(value, candidate).date())
                    break
                except ValueError:
                    continue

    # The review period selector intentionally compresses a shared month or
    # year ("Aug 3–9, 2026" and "Aug 31–Sep 6, 2026"). Expand both visible
    # endpoints so a future week cannot bypass the fixed evidence anchor.
    compact_ranges = (
        (
            rf"\b({month}) (\d{{1,2}})[–—-](\d{{1,2}}), (\d{{4}})\b",
            lambda match: (
                f"{match.group(1)} {match.group(2)}, {match.group(4)}",
                f"{match.group(1)} {match.group(3)}, {match.group(4)}",
            ),
        ),
        (
            rf"\b({month}) (\d{{1,2}})[–—-]({month}) (\d{{1,2}}), (\d{{4}})\b",
            lambda match: (
                f"{match.group(1)} {match.group(2)}, {match.group(5)}",
                f"{match.group(3)} {match.group(4)}, {match.group(5)}",
            ),
        ),
    )
    for pattern, endpoints in compact_ranges:
        for match in re.finditer(pattern, text):
            for value in endpoints(match):
                for candidate in ("%b %d, %Y", "%B %d, %Y"):
                    try:
                        dates.add(dt.datetime.strptime(value, candidate).date())
                        break
                    except ValueError:
                        continue
    return dates


def validate_page_state(
    capture: CaptureSpec, state: dict[str, object], *, auth_token: str
) -> None:
    """Refuse a contaminated viewport before a file can be written."""
    overflow = int(state.get("overflow") or 0)
    if overflow > 0:
        raise RuntimeError(f"{capture.name}: horizontal overflow is {overflow}px")
    exception_count = int(state.get("exceptionCount") or 0)
    if exception_count:
        raise RuntimeError(f"{capture.name}: rendered {exception_count} exception(s)")
    if bool(state.get("coarse")) != capture.coarse_pointer:
        raise RuntimeError(f"{capture.name}: pointer state does not match manifest")
    if not bool(state.get("reduced")):
        raise RuntimeError(f"{capture.name}: reduced-motion emulation is not active")
    scroll_top = int(state.get("scrollTop") or 0)
    if scroll_top:
        raise RuntimeError(
            f"{capture.name}: viewport is scrolled away from the top by {scroll_top}px"
        )
    framework_chrome = int(state.get("frameworkChromeCount") or 0)
    if framework_chrome:
        raise RuntimeError(
            f"{capture.name}: rendered {framework_chrome} framework chrome control(s)"
        )

    text = str(state.get("text") or "")
    if "Sign in to use the AI Partner" in text:
        raise RuntimeError(f"{capture.name}: rendered signed-out Partner clutter")
    if auth_token and auth_token in text:
        raise RuntimeError(f"{capture.name}: rendered a session credential")
    later = sorted(day for day in _dates_in_text(text) if day > CAPTURE_ANCHOR)
    if later:
        raise RuntimeError(
            f"{capture.name}: body contains {later[0]} later than capture anchor "
            f"{CAPTURE_ANCHOR}"
        )


def _token() -> str:
    """A signed session token, so the capture shows the product signed in.

    Deliberately never printed or written to a file. It grants a session:
    echoing it into a terminal, a CI log or a shell scrollback is handing
    out access to the account it was minted for.
    """
    from src.tradelens.ui.components.auth import _issue_token

    return _issue_token(os.environ.get("TL_CAPTURE_USER", CAPTURE_USERNAME), 1)


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

    from src.tradelens.db.models import Trade, User
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

    upsert_strategy_profile(CAPTURE_USER_ID, **demo_strategy_profile())
    trades = load_sample_trades(CAPTURE_USER_ID)

    # load_sample_trades intentionally follows today for ordinary in-product
    # demos. Evidence is different: it must be reproducible. Restamp only this
    # isolated capture database to the fixed anchor after the public loader has
    # built the representative rows.
    weekdays: list[dt.date] = []
    cursor = CAPTURE_ANCHOR
    while len(weekdays) < trades:
        if cursor.weekday() < 5:
            weekdays.append(cursor)
        cursor -= dt.timedelta(days=1)
    weekdays.reverse()
    session = SessionLocal()
    try:
        rows = (
            session.query(Trade)
            .filter(Trade.user_id == CAPTURE_USER_ID, Trade.is_sample == 1)
            .order_by(Trade.id)
            .all()
        )
        if len(rows) != trades:
            raise RuntimeError("capture db sample count changed during anchoring")
        for row, day in zip(rows, weekdays):
            row.trade_date = day.isoformat()
            row.day_of_week = day.strftime("%A")
        session.commit()
    finally:
        session.close()

    # Fail here rather than 40 seconds later with four screenshots of an
    # empty product. Every marketing claim below depends on both of these.
    active = get_active_strategy(CAPTURE_USER_ID)
    if not active or not (active.get("name") or "").strip():
        raise RuntimeError("capture db has no active strategy after seeding")
    missing = [
        field
        for field in demo_strategy_profile()
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
        try:
            self._info = json.load(urllib.request.urlopen(request, timeout=20))
        except Exception as exc:
            raise RuntimeError(f"could not open {redact_url(url)}") from exc
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

    async def box_model(self, selector: str) -> tuple[float, ...]:
        document = await self.send("DOM.getDocument", {"depth": 0})
        node = await self.send(
            "DOM.querySelector",
            {"nodeId": document["root"]["nodeId"], "selector": selector},
        )
        node_id = int(node.get("nodeId") or 0)
        if not node_id:
            raise RuntimeError(f"selector was not rendered: {selector}")
        result = await self.send("DOM.getBoxModel", {"nodeId": node_id})
        return tuple(result["model"]["content"])

    async def mouse(
        self,
        event_type: str,
        *,
        x: float,
        y: float,
        button: str = "none",
        click_count: int = 0,
    ) -> None:
        await self.send(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            },
        )


async def click_center(tab: _Tab, selector: str) -> None:
    """Activate a real rendered control with a trusted CDP pointer sequence."""
    x, y = center_of_box(await tab.box_model(selector))
    await tab.mouse("mouseMoved", x=x, y=y)
    await tab.mouse("mousePressed", x=x, y=y, button="left", click_count=1)
    await tab.mouse("mouseReleased", x=x, y=y, button="left", click_count=1)


async def park_pointer(tab: _Tab) -> None:
    """Move hover state outside the viewport before taking evidence."""
    await tab.mouse("mouseMoved", x=-100, y=-100)


async def _wait_until(tab: _Tab, expression: str, *, failure: str) -> None:
    for _ in range(40):
        time.sleep(1.2)
        if await tab.js(expression):
            return
    raise RuntimeError(failure)


async def _partner_presentations(tab: _Tab) -> int:
    return int(
        await tab.js(
            """
(() => ['.st-key-tl_partner_drawer', '.st-key-tl_partner_page']
  .map(selector => document.querySelector(selector))
  .filter(element => element && getComputedStyle(element).display !== 'none'
    && element.getBoundingClientRect().width > 0
    && element.getBoundingClientRect().height > 0).length)()
"""
        )
        or 0
    )


async def _capture_one(capture: CaptureSpec, token: str) -> Path:
    tab = await _Tab(f"{APP_URL}{capture.route}?auth={token}").open()
    # Same aspect ratio as the declared box, scaled up so more of a tall
    # page fits. deviceScaleFactor 2 on top of that, so the WebP is
    # downsampled from a much denser capture; text taken at 1x and shown on
    # a retina display looks soft.
    css_scale = _MARKETING_VIEWPORT_SCALE.get(capture.name, 1.0)
    view_w = round(capture.width * css_scale)
    view_h = round(capture.height * css_scale)
    await tab.send(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": view_w,
            "height": view_h,
            "deviceScaleFactor": 2,
            "mobile": capture.coarse_pointer,
        },
    )
    await tab.send(
        "Emulation.setTouchEmulationEnabled",
        {"enabled": capture.coarse_pointer, "maxTouchPoints": 5},
    )
    # Marketing stills must not catch a mid-flight entrance animation.
    await tab.send(
        "Emulation.setEmulatedMedia",
        {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
    )

    await _wait_until(
        tab,
        _READY,
        failure=f"{capture.name}: the page never rendered a masthead",
    )

    time.sleep(_SETTLE_SECONDS)

    if capture.name in PREPARE:
        if not await tab.js(PREPARE[capture.name]):
            raise RuntimeError(f"{capture.name}: preparation step found nothing to do")
        time.sleep(1.5)

    if capture.open_partner:
        await click_center(tab, _PARTNER_LAUNCHER)
        await _wait_until(
            tab,
            f"document.querySelectorAll('{_PARTNER_DRAWER_HEADING}').length === 1",
            failure=f"{capture.name}: Partner drawer never opened",
        )
        time.sleep(_SETTLE_SECONDS)

    if capture.open_partner or capture.route == "/Partner":
        presentations = await _partner_presentations(tab)
        if presentations != 1:
            raise RuntimeError(
                f"{capture.name}: rendered {presentations} visible Partner presentations"
            )

    # CDP's page screenshot never paints a cursor. Parking it outside also
    # removes the Streamlit sidebar chevrons and any hover-only tooltip.
    await park_pointer(tab)
    time.sleep(0.5)

    state = await tab.js(_PAGE_STATE)
    if not isinstance(state, dict):
        raise RuntimeError(f"{capture.name}: page-state assertion returned no object")
    validate_page_state(capture, state, auth_token=token)

    shot = await tab.send(
        "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
    )
    raw = base64.b64decode(shot["data"])

    from PIL import Image

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    # Downsample the 2x capture to the declared box.
    if image.size != (capture.width, capture.height):
        image = image.resize((capture.width, capture.height), Image.LANCZOS)

    destination = ROOT / capture.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    if capture.output.suffix == ".webp":
        image.save(destination, "WEBP", quality=_WEBP_QUALITY, method=6)
    elif capture.output.suffix == ".png":
        image.save(destination, "PNG", optimize=True)
    else:
        raise RuntimeError(f"{capture.name}: unsupported output format")
    return destination


def verify(captures: tuple[CaptureSpec, ...] | None = None) -> list[str]:
    """Re-read what was written. Returns a list of problems, empty if clean."""
    from PIL import Image

    captures = captures or (*MARKETING_CAPTURES, *AUDIT_CAPTURES)
    problems: list[str] = []
    for capture in captures:
        path = ROOT / capture.output
        if not path.exists():
            problems.append(f"{capture.name}: {capture.output} was not written")
            continue
        with Image.open(path) as image:
            expected_format = "WEBP" if capture.output.suffix == ".webp" else "PNG"
            if image.format != expected_format:
                problems.append(
                    f"{capture.name}: {image.format}, expected {expected_format}"
                )
            if image.size != (capture.width, capture.height):
                problems.append(
                    f"{capture.name}: {image.size} does not match the "
                    f"declared {(capture.width, capture.height)}"
                )
            metadata = " ".join(f"{key}={value}" for key, value in image.info.items())
            if "auth=" in metadata.lower():
                problems.append(
                    f"{capture.name}: artifact metadata contains an auth query"
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
    await _wait_until(
        tab,
        _READY,
        failure="seed check: the Overview never rendered a masthead",
    )
    note = await tab.js(
        "(()=>{const e=document.querySelector('.tl-side-note');"
        "return e?e.textContent.trim():'';})()"
    )
    if "No active strategy" in (note or ""):
        raise RuntimeError(
            "the running app shows no active strategy — it is not pointed at "
            "a seeded capture database (see --seed / --capture-all)"
        )


async def _capture_manifest(
    captures: tuple[CaptureSpec, ...], token: str
) -> list[Path]:
    destinations = []
    for capture in captures:
        destination = await _capture_one(capture, token)
        destinations.append(destination)
        print(f"  {capture.name:<24} -> {destination.relative_to(ROOT)}")
    return destinations


async def capture_marketing(token: str | None = None) -> list[Path]:
    """Capture the four existing marketing stills from the product viewport."""
    token = token or _token()
    await _assert_app_shows_the_seeded_strategy(token)
    return await _capture_manifest(MARKETING_CAPTURES, token)


async def capture_audit(token: str | None = None) -> list[Path]:
    """Capture every destination plus both responsive Partner presentations."""
    token = token or _token()
    await _assert_app_shows_the_seeded_strategy(token)
    return await _capture_manifest(AUDIT_CAPTURES, token)


async def _main(mode: str) -> int:
    token = _token()
    if mode in {"marketing", "all"}:
        await capture_marketing(token)
    if mode in {"audit", "all"}:
        await capture_audit(token)
    captures = (
        MARKETING_CAPTURES
        if mode == "marketing"
        else (
            AUDIT_CAPTURES
            if mode == "audit"
            else (*MARKETING_CAPTURES, *AUDIT_CAPTURES)
        )
    )
    problems = verify(captures)
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

    try:
        mode = capture_mode(argv)
    except ValueError as exc:
        print(
            f"usage: --marketing | --audit | --all\n       {exc}",
            file=sys.stderr,
        )
        return 2

    from tornado.ioloop import IOLoop

    return IOLoop.current().run_sync(lambda: _main(mode))


if __name__ == "__main__":
    sys.exit(main())
