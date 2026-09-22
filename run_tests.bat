@echo off
cd /d "%~dp0backend"
call .venv\Scripts\activate
pytest -q
pause
