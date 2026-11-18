@echo off
setlocal EnableExtensions
REM AuditProxy Windows setup: create/reuse .venv in this folder.
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
  echo [AuditProxy] Creating local environment: .venv
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERROR: Python 3.10+ is required. Install it before running setup.
      exit /b 1
    )
    python -m venv .venv
  )
  if errorlevel 1 (
    echo ERROR: Could not create .venv
    exit /b 1
  )
) else (
  echo [AuditProxy] Reusing existing .venv
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1
python -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'"
if errorlevel 1 exit /b 1

python -c "from PyQt6.QtWidgets import QApplication" >nul 2>&1
if not errorlevel 1 goto installed

if exist "wheels\*.whl" (
  echo [AuditProxy] Installing from OFFLINE wheels directory...
  python -m pip install --no-index --find-links "%CD%\wheels" -r requirements.txt
) else (
  echo [AuditProxy] No offline wheels found; first-time pip install needs internet access.
  echo             For air-gapped setup, pre-populate wheels for Windows and this Python.
  python -m pip install -r requirements.txt
)
if errorlevel 1 (
  echo ERROR: Failed to install required packages.
  exit /b 1
)

:installed
python -c "from PyQt6.QtWidgets import QApplication; print('[AuditProxy] PyQt6 ready')"
if errorlevel 1 exit /b 1
echo [AuditProxy] Setup complete. Start with run.bat
exit /b 0
