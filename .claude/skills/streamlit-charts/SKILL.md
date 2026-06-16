# Skill: Streamlit Chart Builder

You are building Plotly charts for TradeLens AI's Streamlit UI.

## Design system

- Primary color: teal #20808D
- Accent color: terra #A84B2F
- Background: match Streamlit dark/light theme — use plotly template "plotly_dark" or "plotly_white"
- Font: system default (do not override)

## Rules for every chart

1. ALWAYS test the empty-state — what renders when there are zero trades? Never a raw Plotly error.
   Use: `if df.empty: st.info("No trades yet for this period."); return`
2. Wrap every chart query function in `@st.cache_data(ttl=300)` in the page
3. All aggregation logic lives in services/metrics.py — the page only calls the function and renders
4. Never import pandas or run DB queries directly in a page file
5. Use `st.plotly_chart(fig, use_container_width=True)` for all charts

## Chart inventory (4_Analytics.py)

- Killzone win rate bar chart
- Killzone avg R bar chart
- Killzone profit factor bar chart
- Killzone P&L bar chart
- Confirmation model breakdown
- Mistake tag frequency
- Pattern cards (rendered as st.metric + st.expander, not a chart)
- Edge Leak dollar figure (rendered as st.metric)
- Consistency Score gauge
- Monthly cost by feature (simple bar)

## Chart inventory (3_Calendar.py)

- Month-grid P&L heatmap (Plotly heatmap or annotated table)
- Day drill-down trade list with grade chips
