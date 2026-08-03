# TradeLens AI — Resume Bullets

Five quantified bullets. Past tense, active voice, evidence over adjectives.

- Built an AI post-trade trading journal using Streamlit, SQLAlchemy, and Anthropic's claude-opus-5 (1M-token context, adaptive thinking effort) — routing eight distinct AI pipelines through a single audited client with prompt caching, per-call cost accounting, and a DEMO_MODE that runs the entire app at zero API cost.
- Designed an SMC/ICT-native trade schema (HTF bias, killzones, liquidity sweeps, FVG/OB, BOS/CHoCH) backed by 10 reversible Alembic migrations — every schema change ships with a tested downgrade().
- Engineered a correction-memory loop that stores a trader's label edits and injects them as token-budgeted few-shot context into every AI call, so the model stops repeating mistakes the user already corrected.
- Shipped strategy-aware A–F process grading and a 5-section weekly AI review scored against the user's own rules — verified by 474 tests at 92% service coverage with a CI coverage gate.
- Built a multi-turn AI Partner that reviews completed trades in precise SMC/ICT language with a hard scope guard against signals or predictions, assembling context from trade data, vision analysis, and a prompt-cached strategy profile.
