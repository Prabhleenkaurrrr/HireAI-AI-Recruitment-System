@echo off
cd /d "%~dp0frontend"
py -m http.server 8080
