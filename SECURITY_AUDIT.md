# Security audit

Review of the Flask application against the supplied Node.js security tutorial categories, translated to the existing Python stack. Status describes repository evidence; it is not a third-party certification or production penetration test.

## 1. Input validation and sanitization — IMPROVED

- Registration validates required fields, username syntax and length, email shape and length, password length/complexity, confirmation, and case-insensitive uniqueness in `app/routes/auth.py`.
- Login uses parameterized SQLAlchemy expressions and generic credential errors. Login identity is capped at 254 characters; bcrypt inputs are bounded to 72 bytes and malformed inputs fail closed.
- Request bodies are capped at 16 KiB in `config.py`. Full names reject control characters. Jinja autoescaping is enabled by default. Flask-WTF CSRF remains active.
- Evidence: `tests/test_auth.py`, `tests/test_security.py`; complete suite: 17 passed.
- Limitation: email validation is intentionally pragmatic and does not prove mailbox ownership. Rate limit storage is in-memory.

## 2. Secure authentication — PASS

- Passwords are bcrypt-hashed with cost 12. Login errors are generic, protected routes verify the active user server-side, sessions are cleared before authentication transitions, and logout is a CSRF-protected POST.
- TOTP secrets are encrypted using Fernet; recovery codes are bcrypt-hashed and consumed once.
- Evidence: `app/routes/auth.py`, `app/routes/dashboard.py`, `app/routes/security.py`; tests cover login, protected dashboard, logout, TOTP and recovery-code consumption.
- Limitation: no password reset, email verification, or account lockout flow is implemented.

## 3. Environment variables and secrets — IMPROVED

- Secret key and Fernet key are loaded from environment configuration; non-test startup refuses missing keys. `.env` is ignored and `.env.example` contains placeholders only.
- Local SQLite data and logs are excluded by ignore rules. Existing database was not modified as part of this review.
- Evidence: `config.py`, `app/__init__.py`, `.gitignore`.
- Limitation: secret rotation and deployment secret-manager integration are operational tasks. The existing local `.env` must never be committed.

## 4. SQL injection prevention — PASS

- User lookups use SQLAlchemy expression/query APIs; schema adjustment uses a static SQL statement. No user input is interpolated into SQL.
- Evidence: `app/routes/auth.py`, `app/__init__.py`; ORM-backed authentication and registration tests pass.

## 5. HTTPS and security headers — IMPROVED

- Responses set `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and a restrictive CSP. Sensitive dashboard/security pages use no-store cache controls.
- Session cookies are HTTP-only, SameSite=Lax, and can be made Secure with `COOKIE_SECURE=true` behind HTTPS. HSTS is not enabled for local HTTP.
- Evidence: `app/__init__.py`, `config.py`, `tests/test_dashboard.py`, `tests/test_security.py`.
- Production must terminate HTTPS at a trusted proxy and configure proxy handling, Secure cookies, HSTS at the correct TLS boundary, and CSP review for the chosen deployment.

## 6. Rate limiting and denial-of-service — IMPROVED

- Login, registration, and 2FA verification use Flask-Limiter; request size is capped at 16 KiB.
- Evidence: route decorators in `app/routes/auth.py`, configuration in `config.py`; rate-limit behavior tested in `tests/test_security.py`.
- Limitation: memory storage is process-local and resets at restart. Application limits do not provide complete DDoS defense; production needs shared storage plus reverse-proxy/infrastructure controls.

## 7. Dependency security — IMPROVED

- Runtime/test dependencies are pinned in `requirements.txt`; no Node/npm dependencies are present.
- Evidence: `requirements.txt`. `pip check` could not run because the project venv has no pip module. `pip-audit` was not run; no vulnerability-free claim is made.
- Next verification: run `python -m pip check` and `pip-audit` in a properly provisioned project environment, then review advisories before upgrades.

## 8. Error handling and logging — IMPROVED

- Registration database exceptions are rolled back and shown as generic messages. Login failures do not reveal whether an account exists; credentials and OTP values are not explicitly logged. Production debug mode is not enabled by the app factory.
- Evidence: `app/routes/auth.py`, `run.py`, `config.py`.
- Limitation: a centralized production logging policy and custom friendly 404/500 pages are not implemented. Existing local logs are ignored and were not reviewed for publication; keep them private.

## 9. Security summary — IMPROVED

- Core protections are implemented and covered by 17 passing pytest tests. No new tests were added in this visual/security pass; the existing suite was run.
- Browser verification could not be completed: access to `127.0.0.1:5000` was blocked in this environment, and process inspection was unavailable. No server was started or stopped.
- GitHub publication was not possible: this directory has no `.git` metadata, branch, commit history, or configured remote. No repository was created and nothing was published.
- Database preservation: no database operation was performed. `instance/secure_login.db` and user records were left untouched.
