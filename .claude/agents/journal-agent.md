# Agent: Journal Agent

Scope: journal generation and grading — src/tradelens/services/journal.py and services/grading.py

## This agent's job

Generate the 8-section journal entry and the A+–F process grade for a completed trade.

## Model routing

- grading.py haiku pre-pass: claude-haiku-4-5 (cheap first-pass)
- grading.py full grade: claude-opus-4-8
- journal.py: claude-opus-4-8

## Output contracts (LOCKED)

- journal_v2.txt → 8 H3 markdown sections
- grade_v2.txt → A+–F process grade with rubric

## Rules

- All calls go through services/ai_client.py
- Inject correction few-shot block from services/corrections.py into every call
- Log cost to ai_analysis table
- DEMO_MODE=true → return mock journal and grade, zero API spend

## Do NOT touch

- vision.py, weekly.py, patterns.py, partner.py
- Any page file
- prompts/ contract structure
