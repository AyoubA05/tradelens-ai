"""AI Partner — the full destination, reached from More at phone widths.

The same conversation as the desktop drawer: history is keyed by user, not by
surface, so a question asked in the drawer is still here on a phone and vice
versa. Nothing about the send path changes — this page renders
`render_partner_body` and stops.

There is no floating launcher at these widths, so this page and the drawer can
never both be on screen. That exclusivity is structural, not a CSS trick: the
launcher is `display: none` below the sidebar-navigation width and this route
is only reachable from the bottom bar's More sheet.
"""

import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st  # noqa: E402

from src.tradelens.ui.components.auth import require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.partner_panel import (  # noqa: E402
    SCOPE_NOTE,
    render_partner_body,
)
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.workspace import (  # noqa: E402
    render_workspace_header,
)
from src.tradelens.ui.design_system import inject_design_system  # noqa: E402

st.set_page_config(page_title="AI Partner", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
render_demo_banner()
render_sidebar()

st.markdown(
    render_workspace_header("AI Partner", SCOPE_NOTE),
    unsafe_allow_html=True,
)

# A reflective surface, not a second bright CTA competing with "Log completed
# trade" — the one-primary-action rule still applies here.
render_partner_body(st, surface="page")
