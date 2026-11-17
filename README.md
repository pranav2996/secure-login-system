# Secure Login System

**Your Security. Our Priority.**

A locally hosted Flask authentication application with account registration, bcrypt password storage, protected sessions, optional TOTP two-factor authentication, and one-time recovery codes.

> **Development only:** this project runs on localhost over HTTP. Localhost development is not a production HTTPS deployment. Do not expose the built-in Flask server to the public internet.

## Features

- Registration with server-side validation, unique username/email, and password complexity checks.
- Login by username or email, generic credential errors, inactive account checks, and IP-based rate limits.
- Flask signed sessions, HTTP-only/SameSite cookies, 30-minute idle/absolute session lifetime, and session rotation on sign-in.
- Dashboard protected by authentication and sent with no-store cache headers.
- Optional authenticator-app TOTP, QR setup, encrypted TOTP secret storage, and bcrypt-hashed one-time recovery codes.
- CSRF tokens on all state-changing forms, SQLAlchemy ORM, security headers, responsive templates, and accessible form controls.

## Design and background scenes

Pages share a dark navy glass panel system and locally available system font stack (Inter/Manrope when installed, with Segoe UI/Arial fallbacks). The login page uses the supplied `app/static/video/secure-login-background.mp4` (about 21.8 MiB). Registration, dashboard, 2FA verification/setup, and recovery screens use distinct CSS generated ambient scenes; these require no external assets or requests. Video playback is disabled on small screens, reduced-motion preferences, and low-bandwidth/low-power configurations. All backgrounds are decorative and ignore pointer input.

## Technology and layout

Python 3, Flask, Flask-SQLAlchemy, SQLite for local development, PostgreSQL with Psycopg 3 for deployment, Flask-WTF, Flask-Limiter, bcrypt, PyOTP, qrcode, and pytest. Routes are separated under `app/routes/`; HTML is in `app/templates/`; browser assets are under `app/static/`; automated tests are under `tests/`.

## Prerequisites and setup

Python 3.10 or later is recommended. Git and Node.js are not required. On Windows, `run.bat` checks `%LOCALAPPDATA%\Python\bin\python.exe` and then the Python launcher. If neither exists, install Python from [python.org](https://www.python.org/downloads/windows/). The launcher creates a project-local venv and installs dependencies there.

For manual Windows setup from PowerShell in this project directory:

```powershell
python --version
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m venv --without-pip venv
& "$env:LOCALAPPDATA\Python\bin\python.exe" -m pip --python .\venv\Scripts\python.exe install -r requirements.txt
Copy-Item .env.example .env
```

Before running outside local development, replace both values in `.env` with unique values:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the first output in `SECRET_KEY` and second in `ENCRYPTION_KEY`. Keep `.env` private and backed up. Losing the encryption key makes existing 2FA secrets unreadable. `.env` and the SQLite database are ignored by Git.

## Start on Windows

Double-click `run.bat`, or from PowerShell:

```powershell
Set-Location "C:\Users\prana\Desktop\Secure login page"
.\run.bat
```

The launcher creates `venv` and a unique local `.env` if absent, installs the pinned dependencies in the venv, initializes SQLite on application startup, and binds the development server only to `127.0.0.1:5000`. Open [http://127.0.0.1:5000](http://127.0.0.1:5000). On Linux/macOS run `sh ./run.sh`.

## Deploy to Render

Render serves this Flask application through Gunicorn using the WSGI object `run:app`. Render terminates HTTPS at its load balancer and forwards requests to the service. In production, the app trusts one forwarded proxy hop, requires secure session cookies, keeps CSRF enabled, and checks the PostgreSQL schema without creating or altering it. `/healthz` runs `SELECT 1` and is suitable for Render's health check.

This app currently has one application table, `user`. Production startup refuses SQLite and refuses a missing or incomplete PostgreSQL schema. It does not create tables, seed accounts, or run migrations. Transfer existing users with the explicit migration process below before the first production deploy.

### Create a Neon database

Create a PostgreSQL project in [Neon](https://neon.tech/) and choose the Singapore region if it is offered for your account. In the Neon console, copy the **pooled** connection string for the application role and database. Neon’s pooled hostname includes `-pooler`; keep `sslmode=require`. Treat this URL as a password: do not put it in Git, README, screenshots, or chat. The app normalizes it to the Psycopg 3 SQLAlchemy driver. Do not use a Neon API key or a client-side/JavaScript connection method.

The Neon Free plan currently includes up to 1 GB storage per project and 100 CU-hours per month; compute suspends when idle and wakes on connection. Limits and plan details can change; check [Neon pricing](https://neon.com/pricing) before relying on them.

### Create the Render web service

Connect the GitHub repository and create a Python web service. Render's Free web services have an ephemeral filesystem, which is fine after the app uses Neon because user data resides in PostgreSQL. No disk is used. Set:

| Setting | Value |
| --- | --- |
| Branch | `main` |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT --workers 1 --access-logfile - --error-logfile - run:app` |
| Health check path | `/healthz` |
| Python version | `3.14` (pinned in `.python-version`) |

Render supplies `PORT`; do not set it yourself. The service sleeps after 15 minutes without traffic on the Free plan, so its first request after sleep can take about a minute. Render describes Free services as suitable for hobby/testing, not production workloads; use a paid plan for production availability. See [Render Free](https://render.com/docs/free) for current limits. The rate limiter uses in-memory storage by default; on Free this state resets when the service restarts or sleeps and it does not coordinate across instances. A shared rate-limit store is needed before scaling.

Set these variables in Render's **Environment** page. Enter secret values directly in the dashboard; never add real values to `render.yaml`, Git, README, or chat.

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Neon pooled PostgreSQL connection string with `sslmode=require` |
| `SECRET_KEY` | Use the existing local `.env` value to preserve current signing configuration, or use a planned rotation. Changing it signs out existing sessions. Enter it directly in Render. |
| `ENCRYPTION_KEY` | Use the existing local `.env` value. Changing it makes existing encrypted TOTP secrets unreadable. Enter it directly in Render and keep a secure backup. |
| `COOKIE_SECURE` | `true` (also forced by production configuration) |
| `TRUST_PROXY` | `true` (also forced by production configuration) |
| `RATELIMIT_STORAGE_URI` | Leave unset to use `memory://` for one free instance, or configure a separately managed shared store before scaling. |

Do not set `DATABASE_PATH` on Render. It is retained only for local SQLite compatibility. Production requires `DATABASE_URL` pointing to PostgreSQL.

### Migrate existing local users safely

The migration utility copies the existing SQLite `user` rows, retaining primary keys, password hashes, encrypted TOTP values, pending TOTP values, recovery-code hashes, flags, and timestamps. It opens the SQLite source in read-only mode and never changes it. PostgreSQL changes are append-only: it creates `user` only if the selected schema has no tables, skips byte-for-byte equivalent rows, and aborts on schema mismatches, duplicate identities, or conflicting rows. It does not drop, truncate, update, or delete records. Review and retain a separate secure backup of the local database before proceeding.

Run this from a secure local environment, after installing project requirements and setting `DATABASE_URL` in that environment from your secret store. The command does not read `.env`. Keep the URL out of shell history and logs. The first command is a dry run and prints only row counts and whether the table would be created:

```powershell
.\venv\Scripts\python.exe .\migrate_sqlite_to_postgres.py --source .\instance\secure_login.db
```

Check the output and Neon schema, then only when ready to write run the same command with both explicit flags:

```powershell
.\venv\Scripts\python.exe .\migrate_sqlite_to_postgres.py --source .\instance\secure_login.db --apply --confirm
```

Do not run the apply command until you have reviewed the dry-run result and confirmed that `DATABASE_URL` targets the intended Neon database. Then deploy the app. Startup checks for the complete `user` table and fails closed if it is missing; it will not initialize a blank production database. The source file remains unchanged and excluded from Git.

## Use the app

Create an account with a password of at least eight characters containing a letter, number, and symbol. Sign in with username/email and password. On the dashboard, choose **Set up 2FA**, scan the QR in an authenticator app, and submit the current six-digit code. Save the eight recovery codes; each is one-use. To disable 2FA, provide your password and a current authenticator code. Logout is a CSRF-protected POST.

### Authentication flow

Registration validates the submitted account details and stores a bcrypt password hash. Login accepts a username or email and returns a generic error for invalid credentials. When 2FA is enabled, a successful password check leads to a second step that accepts a time-based authenticator code or a one-time recovery code. The authenticated session then grants access to protected pages. Logging out clears the session.

### Two-factor setup and recovery

From the dashboard, start 2FA setup and scan the displayed QR code in an authenticator app. Confirm setup with a current six-digit TOTP code. The app encrypts the TOTP secret using the configured Fernet key. It displays recovery codes once; store them somewhere private. A recovery code is hashed and consumed when used, and cannot be reused. Keep a secure backup of `ENCRYPTION_KEY`: without it, stored authenticator secrets cannot be decrypted.

### UI/UX highlights

The responsive interface includes registration, login, dashboard, authenticator setup and verification, and recovery-code screens. The login screen uses the included local background video. Other pages use CSS-generated decorative backgrounds. Video playback is disabled for reduced-motion preferences and selected constrained-device settings.

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Tests use isolated temporary SQLite databases. They cover registration validation and duplicates, bcrypt, login, inactive accounts, session protection, logout, cache headers, CSRF, rate limits, TOTP enrollment/login, and one-time recovery code consumption.

## Security and limitations

Passwords are bcrypt hashes with per-password salts; TOTP secrets are encrypted using the environment-held key; recovery codes are individually hashed and consumed on use. ORM queries, CSRF protection, rate limits, output escaping, security headers, and conservative cookie settings reduce common risks. The app deliberately does not log credentials. Render uses Gunicorn, HTTPS-aware proxy handling, secure cookies, and Neon PostgreSQL. The Free deployment's in-memory rate limiter resets when the service restarts and is not shared across multiple instances. There is no email verification, password reset, account lockout, shared rate-limit store, or encryption-key rotation workflow. QR setup content and secrets should be treated as sensitive. Always use a unique `SECRET_KEY` and protect the existing `ENCRYPTION_KEY` when migrating users with 2FA.

## Troubleshooting

- If startup reports missing secrets, run `run.bat` to create a local development `.env`, or configure `SECRET_KEY` and `ENCRYPTION_KEY` manually.
- If package install fails, verify internet access and rerun `venv\Scripts\python.exe -m pip install -r requirements.txt`.
- The local database is created automatically at `instance/secure_login.db`.
- If port 5000 is occupied, stop the other local service before starting this app.
- Avoid deleting or replacing `.env` while encrypted 2FA secrets exist; keep a backup of `ENCRYPTION_KEY`.

See [SECURITY_AUDIT.md](SECURITY_AUDIT.md) for the implementation review and evidence.
