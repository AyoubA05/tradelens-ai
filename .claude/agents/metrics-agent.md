# Agent: Metrics Agent

Scope: analytics computation only — src/tradelens/services/metrics.py

## This agent's job

Compute all aggregations, KPIs, killzone stats, edge leak, consistency score.
Pure pandas — no AI calls, no Streamlit imports, no DB sessions created here.

## Rules

- Every function takes a DataFrame as input and returns a DataFrame or scalar
- Fully unit-tested against fixture DataFrames with known expected values
- No Streamlit imports — ever
- No direct DB queries — data is passed in by the page
- consistency_score() formula must be documented in the docstring

## Functions to implement/maintain

- killzone_stats(df) → DataFrame with win_rate, avg_r, profit_factor, pnl per killzone
- confirmation_model_breakdown(df) → DataFrame
- mistake_tag_frequency(df) → Series
- edge_leak(df) → float (dollar sum of P&L lost on rule violations / mistake tags)
- consistency_score(df) → int 0–100
- monthly_cost_by_feature(ai_analysis_df) → DataFrame

## Do NOT touch

- Any service that makes AI calls
- Any page file
- DB session or models
