# Secrets Setup

TradeLens reads configuration from `.streamlit/secrets.toml` locally and from the
**Streamlit Cloud → App Settings → Secrets** box in production. Keys must be
**top-level** (no `[section]` headers).

```toml
# Login (used only until the first account is created via signup)
TRADELENS_USERNAME = "demo"
TRADELENS_PASSWORD = "tradelens2025"

# Emergency compatibility only. Omit or keep false in normal production.
ENABLE_LEGACY_STREAMLIT_AUTH = "false"

# Invite code that gates account signup. Omit this key to HIDE the signup form.
TRADELENS_INVITE_CODE = "your-invite-code-here"

# AI screenshot analysis (Anthropic)
ANTHROPIC_API_KEY = "sk-ant-..."

# Cached/mock AI output, zero API spend (used for the public demo + tests)
DEMO_MODE = "false"
```

## Login & signup

- **Streamlit login** normally sends unauthenticated visitors to the website
  login. Set `ENABLE_LEGACY_STREAMLIT_AUTH = "true"` only when emergency
  regression access to the old username/password form is required.
- **Sign in** uses the secrets `TRADELENS_USERNAME` / `TRADELENS_PASSWORD` **only
  while the `users` table is empty**. Once anyone signs up, login authenticates
  against bcrypt-hashed DB users and the secrets fallback is ignored.
- **Signup** is invite-gated. The "Create Account" link appears on the login card
  **only when `TRADELENS_INVITE_CODE` is set**. A new account requires the exact
  invite code (compared in constant time). Passwords are hashed with bcrypt —
  plaintext is never stored.
- To run a private, single-user instance: leave `TRADELENS_INVITE_CODE` unset and
  sign in with the secrets credentials.

## Enable AI

Add `ANTHROPIC_API_KEY`. Settings → **AI Status** shows whether it is detected.
Leave `DEMO_MODE = "true"` to explore with cached output at zero API cost.
