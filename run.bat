@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: Could not enter the project folder.
  if not defined SECURE_LOGIN_NO_PAUSE pause
  exit /b 1
)

rem Do not create a second server on the loopback port.
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /C:"127.0.0.1:5000" ^| findstr /C:"LISTENING"') do set "PORT_PID=%%P"
if defined PORT_PID (
  echo ERROR: Port 5000 already has a listener. Process details:
  tasklist /FI "PID eq %PORT_PID%" /FO LIST
  echo The running process was left untouched. If this is Secure Login System, open http://127.0.0.1:5000.
  if not defined SECURE_LOGIN_NO_PAUSE pause
  exit /b 1
)

set "BASEPY=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%BASEPY%" (
  where py >nul 2>nul && set "BASEPY=py -3"
)
if not exist "venv\Scripts\python.exe" (
  echo Creating project virtual environment...
  %BASEPY% -m venv --without-pip venv
  if errorlevel 1 (
    echo Python 3 is required. Install Python from https://www.python.org/downloads/windows/
    if not defined SECURE_LOGIN_NO_PAUSE pause
    exit /b 1
  )
)

echo Installing or checking project dependencies in the local venv...
%BASEPY% -m pip --python venv\Scripts\python.exe install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check network connectivity and retry.
  if not defined SECURE_LOGIN_NO_PAUSE pause
  exit /b 1
)

if not exist ".env" (
  echo Creating a local .env with unique development secrets...
  for /f %%i in ('venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"') do set "SECRET=%%i"
  for /f %%i in ('venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do set "ENC=%%i"
  >.env echo SECRET_KEY=!SECRET!
  >>.env echo ENCRYPTION_KEY=!ENC!
  >>.env echo DATABASE_URL=sqlite:///secure_login.db
  >>.env echo COOKIE_SECURE=false
)

echo Starting Secure Login System at http://127.0.0.1:5000
echo Flask binds only to the local Windows computer. SQLite initializes automatically if needed.
venv\Scripts\python.exe run.py
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" echo ERROR: Flask stopped with exit code %APP_EXIT%. Review the traceback above.
if "%APP_EXIT%"=="0" echo Flask has stopped.
if not defined SECURE_LOGIN_NO_PAUSE pause
exit /b %APP_EXIT%
