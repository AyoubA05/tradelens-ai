# Plan Before Code

Before writing ANY code, produce a plan and then STOP. Do not edit files until I approve.

List, in this order:

1. **Files to create** — full path + one-line purpose for each
2. **Files to modify** — full path + what changes and why
3. **Migrations needed** — Alembic revisions required, with upgrade + downgrade outline (every schema change is reversible)
4. **Tests to add** — test file + what each test asserts (toward the 85+ target)
5. **Conflicts found** — anything that breaks existing contracts, prompts/*_v2.txt, service boundaries, or current passing tests

Then STOP and wait for my explicit approval. Do not write, edit, or run code until I say go.
