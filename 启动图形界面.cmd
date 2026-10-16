@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python app.py
if errorlevel 1 (
  echo.
  echo 启动失败，请确认已安装 Python 3.9 或以上，并包含 Tcl/Tk。
  echo 也可以使用免安装版 CompShareStart.exe。
  pause
)
