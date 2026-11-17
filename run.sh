#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x venv/bin/python ]; then python3 -m venv venv; fi
if [ ! -f .env ]; then
  SECRET="$(venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
  ENC="$(venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || true)"
  if [ -z "$ENC" ]; then venv/bin/python -m pip install cryptography; ENC="$(venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"; fi
  printf 'SECRET_KEY=%s\nENCRYPTION_KEY=%s\nDATABASE_URL=sqlite:///secure_login.db\nCOOKIE_SECURE=false\n' "$SECRET" "$ENC" > .env
fi
venv/bin/python -m pip install -r requirements.txt
exec venv/bin/python run.py
