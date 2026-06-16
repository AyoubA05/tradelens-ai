# /new-trade-review

Trigger the full new trade review workflow:

1. Confirm the trade entry form is open on `1_New_Trade.py`
2. Call `services/vision.py` if a screenshot is attached — pre-fill SMC/ICT fields as editable proposals
3. Run `services/journal.py` to generate the 8-section journal entry
4. Run `services/grading.py` haiku pre-pass first, then full grade if haiku flags it
5. Store everything via `src/tradelens/db/session.py` — never write DB logic in the page
6. Confirm `pytest -q` still passes after any code changes

Hard rules:
- No Streamlit imports in services/
- All AI calls through services/ai_client.py only
- Vision proposals are EDITABLE — never silently overwrite user input
