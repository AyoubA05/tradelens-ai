# AGENTS.md

Maps which sub-agent owns which service in TradeLens AI.
Prevents cross-contamination in parallel Claude sessions.

| Service File | Owner Agent | Model Used |
|---|---|---|
| services/vision.py | vision-agent | claude-opus-5 |
| services/journal.py | journal-agent | claude-opus-5 |
| services/grading.py | journal-agent | claude-opus-5 |
| services/weekly.py | (weekly session) | claude-opus-5 effort=high |
| services/patterns.py | (patterns session) | claude-opus-5 |
| services/corrections.py | (corrections session) | no AI — pure Python |
| services/sessions.py | (schema session) | no AI — pure Python |
| services/metrics.py | metrics-agent | no AI — pure pandas |
| services/partner.py | (partner session) | claude-opus-5 |
| services/ai_client.py | ALL agents route through here | Anthropic SDK wrapper |

## Parallel session rules

- Two sessions may run simultaneously ONLY if they own different service files
- Never run two sessions that both touch services/ai_client.py at the same time
- Use Git Worktrees for parallel sessions:
  git worktree add ../tradelens-corrections week5-corrections
  git worktree add ../tradelens-metrics week5-metrics
