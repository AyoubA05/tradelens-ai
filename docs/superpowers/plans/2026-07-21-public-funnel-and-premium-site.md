# Public Funnel and Premium Marketing Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship one publicly reachable TradeLens marketing experience that hands anonymous visitors into the product's own auth screen, then refine the supplied site into a quieter editorial presentation without changing its core identity.

**Architecture:** Keep the dependency-free static site in `site/`. Extend the existing Python build step so both the canonical site origin and app origin are deployment inputs, add a standard-library public-funnel verifier, and recompose the feature/pricing/FAQ sections with CSS and semantic HTML. Existing motion is reduced to three authored moments; videos are hydrated only when the visitor's device and preferences permit them.

**Tech Stack:** HTML5, CSS custom properties, vanilla JavaScript, Python 3.11 standard library, pytest, Vercel static hosting.

## Global Constraints

- TradeLens remains a post-trade journal and analytics product only; all copy describes completed-trade review.
- Do not add React, a CSS framework, an animation library, or a new dependency.
- Keep Satoshi, Schibsted Grotesk, and JetBrains Mono.
- Keep the charcoal/teal design tokens; reduce teal coverage instead of introducing colors.
- Use no gradient text, decorative icon circles, glassmorphism grids, fake testimonials, or profit claims.
- All app links must be resolved from `APP_ORIGIN` at build time; no production URL is duplicated across HTML and JavaScript.
- WCAG AA, keyboard navigation, reduced motion, explicit image dimensions, and mobile layouts at 375/768/1024/1440 are hard gates.
- The supplied preview URL is not the production destination. Production must be `https://tradelens-ai.com` (with `www` redirecting to the apex), unless the owner changes the canonical domain before execution.
- Preserve unrelated dirty work. Stage exact paths only.

---

## File structure

- `site/index.html` - semantic content and editorial section structure.
- `site/styles.css` - marketing-only tokens, layout, responsive rules, and motion states.
- `site/main.js` - navigation, conditional media hydration, authored motion, and anonymous conversion events.
- `scripts/build_site.py` - validates and resolves canonical and app origins into `dist/site`.
- `scripts/verify_public_funnel.py` - read-only HTTP verifier for the public landing-to-app journey.
- `tests/test_site_metadata.py` - deploy-token and build-output contracts.
- `tests/test_public_funnel.py` - deterministic verifier tests using a local HTTP server.
- `docs/DEPLOY.md` - exact production-domain, Vercel protection, and Streamlit visibility checklist.

---

### Task 1: Make both production origins explicit

**Files:**
- Modify: `scripts/build_site.py:24-113`
- Modify: `site/index.html:14-27,65,89,315,370,374`
- Modify: `site/main.js:1-11`
- Modify: `vercel.json:1-7`
- Modify: `tests/test_site_metadata.py:1-142`

**Interfaces:**
- Consumes: environment variables `SITE_ORIGIN: str` and `APP_ORIGIN: str`.
- Produces: `build(site_origin: str, app_origin: str, src: Path = SRC, out: Path = OUT) -> Path`; deploy tokens `__SITE_ORIGIN__` and `__APP_ORIGIN__` exist only in source and never in `dist/site`.

- [x] **Step 1: Write failing tests for the second origin**

Add to `tests/test_site_metadata.py`:

```python
APP = "https://tradelens-app.streamlit.app"


def test_source_uses_app_origin_token():
    text = _index_text()
    assert "__APP_ORIGIN__" in text
    assert APP not in text


def test_build_resolves_site_and_app_origins(tmp_path):
    out = build(REAL, APP, out=tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    js = (out / "main.js").read_text(encoding="utf-8")
    assert "__SITE_ORIGIN__" not in html
    assert "__APP_ORIGIN__" not in html + js
    assert f'href="{APP}"' in html
    assert f'const APP_URL = "{APP}"' in js


def test_missing_app_origin_is_rejected(tmp_path):
    with pytest.raises(BuildError, match="APP_ORIGIN"):
        build(REAL, "", out=tmp_path / "site")
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest tests/test_site_metadata.py -q`  
Expected: FAIL because `build()` accepts only one origin and the app token is absent.

- [x] **Step 3: Extend the build interface**

In `scripts/build_site.py`, define both tokens and replace `build()`/`main()` with:

```python
SITE_TOKEN = "__SITE_ORIGIN__"
APP_TOKEN = "__APP_ORIGIN__"
TOKEN = SITE_TOKEN  # backward-compatible import for existing tests


def build(site_origin: str, app_origin: str, src: Path = SRC, out: Path = OUT) -> Path:
    site_origin = validate_origin(site_origin)
    try:
        app_origin = validate_origin(app_origin)
    except BuildError as exc:
        raise BuildError(f"APP_ORIGIN is invalid: {exc}") from exc

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    replacements = {SITE_TOKEN: site_origin, APP_TOKEN: app_origin}

    for path in out.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace(token, value)
        path.write_text(text, encoding="utf-8")

    leftovers = []
    for path in out.rglob("*"):
        if path.is_file() and path.suffix.lower() in _TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in replacements):
                leftovers.append(str(path.relative_to(out)))
    if leftovers:
        raise BuildError(f"deploy token survived in: {', '.join(leftovers)}")
    return out


def main() -> int:
    try:
        out = build(
            os.getenv("SITE_ORIGIN", ""),
            os.getenv("APP_ORIGIN", ""),
        )
    except BuildError as exc:
        print(f"build_site: {exc}", file=sys.stderr)
        return 1
    print(f"build_site: wrote {out}")
    return 0
```

- [x] **Step 4: Replace every hard-coded app URL**

Set `const APP_URL = "__APP_ORIGIN__";` in `site/main.js`. Replace every `href="https://tradelens-app.streamlit.app"` in `site/index.html` with `href="__APP_ORIGIN__"`.

- [x] **Step 5: Set deployment inputs**

Replace `vercel.json` with:

```json
{
  "buildCommand": "python3 scripts/build_site.py",
  "outputDirectory": "dist/site",
  "env": {
    "SITE_ORIGIN": "https://tradelens-ai.com",
    "APP_ORIGIN": "https://tradelens-app.streamlit.app"
  }
}
```

- [x] **Step 6: Update old test calls and verify**

Change every `build(REAL, out=...)` call in `tests/test_site_metadata.py` to `build(REAL, APP, out=...)`.

Run: `.venv/bin/python -m pytest tests/test_site_metadata.py -q`  
Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add scripts/build_site.py site/index.html site/main.js vercel.json tests/test_site_metadata.py
git commit -m "site: make canonical and app origins deploy inputs"
```

### Task 2: Add an anonymous public-funnel verifier

**Files:**
- Create: `scripts/verify_public_funnel.py`
- Create: `tests/test_public_funnel.py`
- Modify: `docs/DEPLOY.md`

**Interfaces:**
- Produces: `check_endpoint(url: str, forbidden_hosts: tuple[str, ...] = ()) -> CheckResult` and CLI exit code 0 only when the landing returns HTML and the app does not leave the visitor at provider-level authentication.

- [x] **Step 1: Write the verifier tests**

Create `tests/test_public_funnel.py` with a local `ThreadingHTTPServer` fixture covering: 200 HTML passes, provider-auth redirect fails, wrong marketing title fails, and network errors return a clear failure result.

```python
from scripts.verify_public_funnel import classify


def test_public_marketing_page_passes():
    result = classify(200, "https://tradelens-ai.com/", "<title>TradeLens AI</title>")
    assert result.ok


def test_provider_auth_redirect_fails():
    result = classify(303, "https://share.streamlit.io/-/auth/app", "")
    assert not result.ok
    assert "provider authentication" in result.detail


def test_wrong_marketing_version_fails():
    html = "<title>TradeLens AI — Behavioral Trading Analytics & AI Coaching</title>"
    result = classify(200, "https://tradelens-ai.com/", html)
    assert not result.ok
    assert "unexpected title" in result.detail
```

- [x] **Step 2: Run the tests and verify failure**

Run: `.venv/bin/python -m pytest tests/test_public_funnel.py -q`  
Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement the verifier**

Create `scripts/verify_public_funnel.py` using only `urllib.request`, `urllib.error`, `dataclasses`, and `argparse`. `classify()` must reject URLs containing `/sso-api`, `share.streamlit.io/-/auth`, or `/-/login`; marketing HTML must contain the chosen site title `TradeLens AI — Post-Trade Journal. AI-Powered Growth.`. The CLI accepts `--site` and `--app`, prints one line per check, and exits 1 on any failure.

- [x] **Step 4: Document the external settings that code cannot change**

Append this exact release gate to `docs/DEPLOY.md`:

```markdown
## Public funnel release gate

1. Vercel Production Deployment Protection: Off.
2. `tradelens-ai.com` points to this repository's production deployment.
3. `www.tradelens-ai.com` redirects once to `https://tradelens-ai.com/`.
4. Streamlit app visibility is Public so anonymous visitors reach TradeLens auth.
5. Run:
   `.venv/bin/python scripts/verify_public_funnel.py --site https://tradelens-ai.com --app https://tradelens-app.streamlit.app`
6. Expected: two PASS lines and exit code 0.
```

- [x] **Step 5: Verify**

Run: `.venv/bin/python -m pytest tests/test_public_funnel.py -q`  
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add scripts/verify_public_funnel.py tests/test_public_funnel.py docs/DEPLOY.md
git commit -m "deploy: verify anonymous landing-to-app funnel"
```

### Task 3: Replace the bento grid with three editorial product stories

**Files:**
- Modify: `site/index.html:109-212`
- Modify: `site/styles.css:477-601,1038-1064`
- Modify: `tests/test_site_metadata.py`

**Interfaces:**
- Produces: `.story-list`, `.story`, `.story-copy`, `.story-proof`, and `.story-facts`; only three large screenshots are used above the fold of the feature narrative.

- [x] **Step 1: Add a failing structural test**

```python
def test_feature_section_uses_editorial_stories_not_bento_cards():
    html = _index_text()
    assert html.count('class="story"') == 3
    assert "feature-grid" not in html
    assert "card-icon" not in html
```

- [x] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_site_metadata.py -q -k editorial`  
Expected: FAIL.

- [x] **Step 3: Replace the feature markup**

Use three `<article class="story">` elements:

1. **Review the trade** - screenshot upload, structured journal, psychology notes; use `shot-newtrade.webp`.
2. **Measure the process** - calendar, setup performance, risk and consistency; use `shot-analytics.webp`.
3. **Build discipline** - strategy profile, evidence-backed review, weekly recap; use `shot-strategy.webp`.

Each article contains one heading, one 2-3 sentence paragraph, a three-item unboxed list, and one `<figure>` with a specific alt and a one-sentence `<figcaption>`. Do not place SVG icons beside the headings.

- [x] **Step 4: Replace bento styling with editorial styling**

Delete `.card-head`, `.card-icon`, `.feature-grid`, `.card-wide`, and `.card-full*` rules. Add a neutral ledger layout:

```css
.story-list { border-top: 1px solid var(--border); }
.story {
  display: grid;
  grid-template-columns: minmax(250px, .8fr) minmax(0, 1.6fr);
  gap: clamp(32px, 6vw, 88px);
  align-items: center;
  padding-block: clamp(56px, 8vw, 104px);
  border-bottom: 1px solid var(--border);
}
.story:nth-child(even) .story-copy { order: 2; }
.story-copy h3 { font-size: clamp(1.5rem, 2.4vw, 2.15rem); }
.story-copy > p { margin-top: 16px; color: var(--muted); max-width: 46ch; }
.story-facts { margin: 24px 0 0; padding: 0; list-style: none; }
.story-facts li { padding-block: 9px; border-top: 1px solid var(--border); }
.story-proof { margin: 0; }
.story-proof .shot-frame { border-bottom: 1px solid var(--border); border-radius: 12px; }
.story-proof figcaption { margin-top: 12px; color: var(--muted); font-size: .8125rem; }
@media (max-width: 760px) {
  .story { grid-template-columns: 1fr; gap: 28px; }
  .story:nth-child(even) .story-copy { order: initial; }
}
```

- [x] **Step 5: Verify and commit**

Run: `.venv/bin/python -m pytest tests/test_site_metadata.py -q`  
Expected: PASS.

```bash
git add site/index.html site/styles.css tests/test_site_metadata.py
git commit -m "site: replace feature bento with editorial product stories"
```

### Task 4: Quiet the visual system and fix under-composed sections

**Files:**
- Modify: `site/index.html:214-365`
- Modify: `site/styles.css:102-158,603-988`

**Interfaces:**
- Consumes: existing palette and typography.
- Produces: one vertical workflow rail, a centered beta offer, and a two-column FAQ composition.

- [x] **Step 1: Remove ambient glow elements and animations**

Delete `.glow-a`/`.glow-b` markup, `.glow*` CSS, and `drift-a`/`drift-b` keyframes. Keep the subtle grain at `opacity: 0.025`.

- [x] **Step 2: Simplify the AI workflow**

Replace five rounded `.wizard-chip` boxes with a single ordered list using a 1px vertical line and small mono step numbers. Use neutral text for inactive steps and teal only for the current first step shown in the screenshot.

- [x] **Step 3: Recompose pricing**

Change `.tier-grid` to `grid-template-columns: minmax(0, 520px); justify-content:center;`. Remove the gradient inherited from `.card`; use `background: var(--surface)` and one neutral border. Change the action label to `Start your journal` everywhere.

- [x] **Step 4: Recompose FAQ**

Wrap the FAQ heading and list in `.faq-layout` and apply:

```css
.faq-layout {
  display: grid;
  grid-template-columns: minmax(220px, .65fr) minmax(0, 1.35fr);
  gap: clamp(40px, 8vw, 112px);
  align-items: start;
}
.faq-layout .section-head { position: sticky; top: 108px; margin: 0; }
.faq-list { max-width: none; }
@media (max-width: 760px) {
  .faq-layout { grid-template-columns: 1fr; gap: 28px; }
  .faq-layout .section-head { position: static; }
}
```

- [x] **Step 5: Verify responsive composition**

Serve `dist/site` locally and capture 375/768/1024/1440 screenshots. Expected: no stranded pricing card, no empty right half of FAQ, no horizontal overflow, and teal occupies only actions/active states.

- [x] **Step 6: Commit**

```bash
git add site/index.html site/styles.css
git commit -m "site: quiet decoration and rebalance pricing and faq"
```

### Task 5: Prevent unnecessary video requests and limit motion

**Files:**
- Modify: `site/index.html:71-75,248-252`
- Modify: `site/main.js:1-195`
- Modify: `site/styles.css:368-469`

**Interfaces:**
- Produces: `hydrateEligibleVideos(): void`; no MP4 source exists in initial HTML.

- [x] **Step 1: Change video source markup**

Replace each `<source src="...">` with a `<video data-video-src="assets/...mp4" ...>` element containing no source child.

- [x] **Step 2: Replace source removal with source hydration**

```javascript
function hydrateEligibleVideos() {
  if (smallScreen || reducedMotion || saveData) return;
  document.querySelectorAll("video[data-video-src]").forEach((video) => {
    const source = document.createElement("source");
    source.src = video.dataset.videoSrc;
    source.type = "video/mp4";
    video.appendChild(source);
    video.load();
    video.play().catch(() => {});
  });
}

hydrateEligibleVideos();
```

- [x] **Step 3: Reduce motion to three authored moments**

Keep hero word entrance, showcase tilt, and workflow line draw. Remove generic `[data-reveal]` from individual story/pricing/FAQ items and delete the IntersectionObserver block. All content is visible by default.

- [x] **Step 4: Verify**

At 375px and reduced-motion desktop, Network must show zero `.mp4` requests. At normal desktop, both MP4 files may load after JavaScript executes. Content must remain complete without JavaScript.

- [x] **Step 5: Commit**

```bash
git add site/index.html site/main.js site/styles.css
git commit -m "site: hydrate media conditionally and reduce motion noise"
```

### Task 6: Add privacy-safe conversion events and final verification

**Files:**
- Modify: `site/index.html`
- Modify: `site/main.js`
- Modify: `tests/test_site_metadata.py`

**Interfaces:**
- Produces events `marketing_cta_click` with property `location` and `faq_open` with property `question`; no username, account ID, trade data, or free-text answer is sent.

- [x] **Step 1: Label action locations**

Add `data-cta-location="nav|hero|pricing|final|mobile"` to the five primary links.

- [x] **Step 2: Add event wiring**

```javascript
function track(name, properties) {
  if (typeof window.va === "function") window.va("event", { name, ...properties });
}

document.querySelectorAll("[data-cta-location]").forEach((link) => {
  link.addEventListener("click", () => {
    track("marketing_cta_click", { location: link.dataset.ctaLocation });
  });
});

document.querySelectorAll(".faq-item").forEach((item) => {
  item.addEventListener("toggle", () => {
    if (item.open) track("faq_open", { question: item.querySelector("summary").textContent });
  });
});
```

- [x] **Step 3: Add a source contract test**

Assert there are exactly five `data-cta-location` attributes and that `main.js` contains no references to password, username, trade, P&L, notes, or screenshot fields.

- [x] **Step 4: Run the complete relevant suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_site_metadata.py tests/test_public_funnel.py -q
.venv/bin/ruff check scripts/build_site.py scripts/verify_public_funnel.py tests/test_site_metadata.py tests/test_public_funnel.py
SITE_ORIGIN=https://tradelens-ai.com APP_ORIGIN=https://tradelens-app.streamlit.app .venv/bin/python -m scripts.build_site
```

Expected: all tests pass, ruff clean, build writes `dist/site` with no unresolved token.

- [x] **Step 5: Perform public release verification**

After production deploy and visibility settings are applied, run:

```bash
.venv/bin/python scripts/verify_public_funnel.py \
  --site https://tradelens-ai.com \
  --app https://tradelens-app.streamlit.app
```

Expected: two PASS lines and exit 0.

- [x] **Step 6: Commit**

```bash
git add site/index.html site/main.js tests/test_site_metadata.py
git commit -m "site: measure anonymous conversion without personal data"
```

