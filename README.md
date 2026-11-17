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

Python 3, Flask, Flask-SQLAlchemy, SQLite, Flask-WTF, Flask-Limiter, bcrypt, PyOTP, qrcode, and pytest. Routes are separated under `app/routes/`; HTML is in `app/templates/`; browser assets are under `app/static/`; automated tests are under `tests/`.

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

Render serves this Flask application through Gunicorn using the WSGI object `run:app`. Render terminates HTTPS at its load balancer and forwards requests to the service. The production configuration trusts one forwarded proxy hop, marks session cookies `Secure`, and still requires CSRF protection. The `/healthz` endpoint executes a small database query and is suitable for Render's HTTP health check.

### Create the Render web service

Connect the private GitHub repository and create a **paid Python web service**. A persistent disk is required for SQLite; Render does not provide persistent disks for Free web services. Configure:

| Setting | Value |
| --- | --- |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn --bind 0.0.0.0:$PORT --workers 1 --access-logfile - --error-logfile - run:app` |
| Health check path | `/healthz` |
| Persistent disk mount path | `/var/data` |
| Python version | `3.14` (also pinned in `.python-version`) |

The single Gunicorn worker and single Render instance avoid concurrent multi-process writes to SQLite. Do not scale this SQLite service horizontally. The rate limiter uses in-memory storage and is process-local; use a shared production rate-limit store before running multiple app processes or instances.

Set these values in the Render service's **Environment** page. Do not put real secret values in `render.yaml`, Git, or chat.

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `SECRET_KEY` | Generate a long random secret with `python -c "import secrets; print(secrets.token_hex(32))"` and enter it directly in Render. Changing it later signs out existing sessions. |
| `ENCRYPTION_KEY` | The current local `.env` value if you are migrating existing users with 2FA; changing it makes their stored TOTP secrets unreadable. Enter it directly in Render and keep a secure backup. |
| `DATABASE_PATH` | `/var/data/secure_login.db` after the database copy is in place |
| `COOKIE_SECURE` | `true` |
| `TRUST_PROXY` | `true` |

Render supplies `PORT`; do not hard-code or manually set it. The application refuses production startup if `DATABASE_PATH` is missing or if its database file is absent. It will not silently create a new empty production database. `DATABASE_URL` remains supported for local use and compatibility, but use `DATABASE_PATH` for the Render SQLite disk.

### Preserve and transfer the existing SQLite database

The local database is deliberately not part of Git, and deploying source code does not transfer its users. Render disks are available only at runtime, are attached to a paid service, and preserve only files under their mount path. Seed the disk with a verified backup before opening the app to users. This process creates a separate backup copy and never replaces or edits the original local database.

1. In PowerShell at the project root, make a consistent SQLite online backup to a new, uniquely named local file:

   ```powershell
   $env:DB_COPY = Join-Path $PWD ("secure-login-migration-" + [guid]::NewGuid().ToString("N") + ".db")
   @'
   import os, sqlite3
   from pathlib import Path
   source_path = Path("instance/secure_login.db").resolve()
   source = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
   destination_path = os.environ["DB_COPY"]
   if os.path.exists(destination_path):
       raise SystemExit("Refusing to replace an existing backup file")
   destination = sqlite3.connect(destination_path)
   source.backup(destination)
   result = destination.execute("PRAGMA integrity_check").fetchone()[0]
   destination.close()
   source.close()
   if result != "ok":
       raise SystemExit("Backup integrity check failed")
   print("Verified database backup created")
   '@ | .\venv\Scripts\python.exe -
   ```

2. Create the paid web service with the `/var/data` disk. For the first deploy only, set `DATABASE_PATH=/var/data/secure-login-bootstrap.db`, `APP_ENV=production`, `MAINTENANCE_MODE=true`, and `ALLOW_DATABASE_INIT=true`. Add the secrets above. The app will create a separate empty bootstrap database, keep application routes at HTTP 503, and leave `/healthz` available so the instance can become healthy. Do not share the service URL during this temporary maintenance period.
3. Set up SSH for the paid Render service, then copy the backup to a new path on the mounted disk. Replace the local filename, service name, and region with your actual values:

   ```powershell
   scp -s $env:DB_COPY YOUR_SERVICE@ssh.YOUR_REGION.render.com:/var/data/secure_login_imported.db
   ```

   Do not use an existing destination filename. In the Render Shell, verify the copied file without displaying user data:

   ```sh
   python -c "import sqlite3; c=sqlite3.connect('file:/var/data/secure_login_imported.db?mode=ro', uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
   ```

4. In Render, change `DATABASE_PATH` to `/var/data/secure_login_imported.db`, set `MAINTENANCE_MODE=false` and `ALLOW_DATABASE_INIT=false`, then redeploy. Keep the original local database and the verified local backup safe. The bootstrap file remains separate and is not used by the app.

Back up the persistent disk regularly. A Render persistent disk is attached to one service instance and prevents scaling that service to multiple instances. For higher availability or concurrent scaling, plan a separately reviewed migration to managed PostgreSQL; do not point this SQLite application at an ephemeral filesystem.

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

Passwords are bcrypt hashes with per-password salts; TOTP secrets are encrypted using the environment-held key; recovery codes are individually hashed and consumed on use. ORM queries, CSRF protection, rate limits, output escaping, security headers, and conservative cookie settings reduce common risks. The app deliberately does not log credentials. The built-in server and in-memory rate limiter are for local development; Render uses Gunicorn, HTTPS-aware proxy handling, secure cookies, and a persistent disk for SQLite. There is no email verification, password reset, account lockout, shared rate-limit store, or encryption-key rotation workflow. QR setup content and secrets should be treated as sensitive. Always use a unique `SECRET_KEY` and protect the existing `ENCRYPTION_KEY` when migrating users with 2FA.

## Troubleshooting

- If startup reports missing secrets, run `run.bat` to create a local development `.env`, or configure `SECRET_KEY` and `ENCRYPTION_KEY` manually.
- If package install fails, verify internet access and rerun `venv\Scripts\python.exe -m pip install -r requirements.txt`.
- The local database is created automatically at `instance/secure_login.db`.
- If port 5000 is occupied, stop the other local service before starting this app.
- Avoid deleting or replacing `.env` while encrypted 2FA secrets exist; keep a backup of `ENCRYPTION_KEY`.

See [SECURITY_AUDIT.md](SECURITY_AUDIT.md) for the implementation review and evidence.
