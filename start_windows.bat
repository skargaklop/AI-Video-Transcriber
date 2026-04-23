@echo off
setlocal
cd /d "%~dp0"

echo Installing / updating dependencies...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: pip install failed. Make sure Python is installed and on your PATH.
  pause
  exit /b 1
)

set PORT=8001
python start.py --prod
