# /analytics-check

Verify all analytics charts render correctly:

1. Run the app with seed data loaded — confirm `python scripts/seed.py` seeded 60 trades
2. Open `4_Analytics.py` — verify all sections render: KPIs, Killzone Performance, Pattern Cards, Edge Leak
3. Open `3_Calendar.py` — verify month heatmap renders, day drill-down works, empty month shows branded state
4. Check every chart has an empty-state fallback (not a raw Plotly error)
5. Confirm teal #20808D is the primary chart color, terra #A84B2F is the accent
6. Run Playwright MCP end-to-end if available

Hard rules:
- All chart aggregation logic lives in services/metrics.py — pages only render
- st.cache_data on every metrics function that queries the DB
