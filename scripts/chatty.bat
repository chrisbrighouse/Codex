@echo off
setlocal
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%\..
py -3 -m src.main %*

