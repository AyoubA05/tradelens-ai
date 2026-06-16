# /week-review

Trigger the weekly AI review workflow:

1. Call `services/weekly.py` — gather last 7 days of trades, metrics, top patterns, correction history
2. Use `claude-opus-4-8` with `prompts/weekly_v2.txt` — effort="high"
3. Persist result to `weekly_reviews` table — if week already exists, ask for confirm before overwriting
4. Render on `6_Weekly_Review.py` — week picker, 5 H3 sections, stats sidebar, thinking summary expander
5. If zero trades in the selected week — show friendly empty state, do NOT make an API call
6. Confirm `pytest -q` still passes after any code changes

Hard rules:
- prompts/weekly_v2.txt is LOCKED — do not rewrite it
- All AI calls through services/ai_client.py only
- Log cost_usd to ai_analysis table on every call
