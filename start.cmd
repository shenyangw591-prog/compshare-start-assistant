@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python start_instance.py
echo.
pause
