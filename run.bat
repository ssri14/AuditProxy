@echo off
setlocal EnableExtensions
REM AuditProxy Windows launcher; safe to double-click from Explorer.
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import PyQt6.QtWidgets" >nul 2>&1
if errorlevel 1 goto setup
goto launch

:setup
call "%~dp0setup.bat"
if errorlevel 1 (
  echo.
  echo ERROR: Setup failed. Review the message above.
  pause
  exit /b 1
)

:launch
call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1
python app.py %*
if errorlevel 1 (
  echo.
  echo ERROR: AuditProxy exited unexpectedly.
  pause
  exit /b 1
)
exit /b 0
