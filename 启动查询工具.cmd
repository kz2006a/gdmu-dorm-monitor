@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 run.py
  exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw run.py
  exit /b
)
echo Python was not found. Install Python and run: python -m pip install -r requirements.txt
pause
