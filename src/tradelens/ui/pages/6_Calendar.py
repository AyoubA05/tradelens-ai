import sys
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import calendar as _calendar  # noqa: E402
import datetime  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.metrics import calendar_daily_pnl  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.ui.components.charts import calendar_heatmap_chart  # noqa: E402

st.set_page_config(page_title="Calendar", page_icon="🗓️", layout="wide")
st.title("🗓️ Trade Calendar")

_GRADE_COLORS = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}


def _val(x):
    """Return None for pandas NA/NaN, else the value (keeps truthiness checks honest)."""
    return None if pd.isna(x) else x


@st.cache_data(ttl=60)
def _load_df() -> pd.DataFrame:
    trades = get_trades()
    return pd.DataFrame(
        [
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "asset": t.asset,
                "result": t.result,
                "pnl": t.pnl,
                "killzone": t.killzone,
                "ai_grade": t.ai_grade,
                "user_grade": t.user_grade,
            }
            for t in trades
        ]
    )


df = _load_df()

if df.empty:
    st.info("You haven't logged any trades yet. Head to New Trade to get started.")
    st.stop()

# --- Month navigation (session-state) ---
today = datetime.date.today()
if "cal_year" not in st.session_state:
    st.session_state["cal_year"] = today.year
    st.session_state["cal_month"] = today.month


def _shift_month(delta: int) -> None:
    y, m = st.session_state["cal_year"], st.session_state["cal_month"]
    m += delta
    if m < 1:
        m, y = 12, y - 1
    elif m > 12:
        m, y = 1, y + 1
    st.session_state["cal_year"], st.session_state["cal_month"] = y, m


nav_prev, nav_title, nav_next = st.columns([1, 3, 1])
with nav_prev:
    st.button("◀ Prev", on_click=_shift_month, args=(-1,), use_container_width=True)
with nav_next:
    st.button("Next ▶", on_click=_shift_month, args=(1,), use_container_width=True)

year = st.session_state["cal_year"]
month = st.session_state["cal_month"]
with nav_title:
    st.markdown(
        f"<h3 style='text-align:center'>{_calendar.month_name[month]} {year}</h3>",
        unsafe_allow_html=True,
    )

# --- Month aggregation (all logic in metrics.py) ---
daily = calendar_daily_pnl(df, year, month)

if daily.empty:
    st.info(
        f"No trades in {_calendar.month_name[month]} {year}. "
        "Use ◀ / ▶ above to pick another month."
    )
    st.stop()

# --- Month KPIs ---
net = float(daily["net_pnl"].sum())
total_trades = int(daily["trades"].sum())
total_wins = int(daily["wins"].sum())
win_rate = (total_wins / total_trades) if total_trades else 0.0

k1, k2, k3 = st.columns(3)
k1.metric("Month Net P/L", f"${net:,.2f}")
k2.metric("Trades", total_trades)
k3.metric("Win Rate", f"{win_rate:.1%}")

# --- Heatmap ---
st.plotly_chart(calendar_heatmap_chart(daily, year, month), use_container_width=True)

# --- Day drill-down (select a day with trades → list with grade chips) ---
st.markdown("#### Day Detail")
days_with_trades = [int(d) for d in daily["day"].tolist()]
selected_day = st.selectbox(
    "Select a day with trades",
    options=days_with_trades,
    format_func=lambda d: f"{_calendar.month_name[month]} {d}, {year}",
)

date_str = f"{year:04d}-{month:02d}-{selected_day:02d}"
day_trades = df[df["trade_date"].astype(str) == date_str]

if day_trades.empty:
    st.caption("No trades on this day.")
else:
    for _, tr in day_trades.iterrows():
        grade = _val(tr.get("user_grade")) or _val(tr.get("ai_grade"))
        chip = f"{_GRADE_COLORS.get(grade, '⚪')} {grade}" if grade else "⚪ —"
        pnl = _val(tr.get("pnl"))
        pnl_str = f"${pnl:,.2f}" if pnl is not None else "—"
        kz = _val(tr.get("killzone")) or "—"
        result = _val(tr.get("result")) or "?"
        st.markdown(
            f"**#{int(tr['id'])}** · {tr['asset']} · {result} · "
            f"P/L {pnl_str} · Killzone `{kz}` · Grade {chip}"
        )
