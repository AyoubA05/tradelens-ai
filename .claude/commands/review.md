# Pre-Commit Code Review Checklist

Before every commit verify:
- [ ] pytest -q passes (all old + new tests green)
- [ ] ruff check . passes
- [ ] black --check . passes
- [ ] No hardcoded API keys or secrets
- [ ] No stack traces exposed to UI (typed errors only)
- [ ] DEMO_MODE=true path tested
- [ ] Commit message format: week5-d<N>: <summary>
