@echo off
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -m venv .venv
)
call .venv\Scripts\activate
if not exist ".installed" (
  echo Installing dependencies...
  pip install -r requirements.txt
  if errorlevel 1 pause & exit /b 1
  echo installed> .installed
)
if not exist ".env" (
  copy .env.example .env
  echo.
  echo IMPORTANT: Open backend\.env and add your Foundry API key before using AI analysis.
  echo.
)
uvicorn main:app --reload --port 8000
